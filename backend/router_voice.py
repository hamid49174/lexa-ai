"""Lexa AI — Voice Router v3
Thin API layer for STT, TTS, Wake Word + Conversation Mode.
All conversation logic lives in voice/conversation.py.
"""

import asyncio
import logging
import re
import tempfile
import threading
import time as _time
import uuid as _uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.agent_protocol import redacted_summary
from backend.security import check_rate_limit, audit_log
from backend.i18n import t
from backend.voice_ws import (
    push_event, push_volume, push_state,
    pop_fallback_events, register_ws_client, unregister_ws_client,
)
from voice.config import (
    WAKE_ENGINE,
    WAKE_FALLBACK_STT_BACKOFF_STEP_S,
    WAKE_FALLBACK_STT_MAX_INTERVAL_S,
    WAKE_FALLBACK_STT_MIN_INTERVAL_S,
    WAKE_OPENWAKEWORD_AUTO_DOWNLOAD,
    WAKE_OPENWAKEWORD_MODELS,
    WAKE_OPENWAKEWORD_PATIENCE,
    WAKE_OPENWAKEWORD_THRESHOLD,
    WAKE_OPENWAKEWORD_VAD_THRESHOLD,
    WAKE_PHRASES,
    MAX_TTS_TEXT_CHARS,
)

# Single source of truth fuer den Default-Sensitivity-Wert, damit Request-Default,
# Status-Default und Fallback nicht auseinanderlaufen.
_DEFAULT_WAKE_SENSITIVITY = 0.015

# ═══════════════════════════════════════════════════
#  REQUEST MODELS
# ═══════════════════════════════════════════════════


class TTSRequest(BaseModel):
    text: str = ""


class STTModelRequest(BaseModel):
    model: str = "base"


class STTLanguageRequest(BaseModel):
    language: str = "de"


class STTEngineRequest(BaseModel):
    engine: str = "deepgram"


class DeepgramKeyRequest(BaseModel):
    api_key: str = ""


class SensitivityRequest(BaseModel):
    sensitivity: float = _DEFAULT_WAKE_SENSITIVITY


class ElevenLabsKeyRequest(BaseModel):
    api_key: str = ""


class ElevenLabsVoiceRequest(BaseModel):
    voice_id: str = ""


class ElevenLabsModelRequest(BaseModel):
    model: str = "eleven_multilingual_v2"


class ElevenLabsSettingsRequest(BaseModel):
    stability: float | None = None
    similarity: float | None = None
    style: float | None = None


class ElevenLabsToggleRequest(BaseModel):
    enabled: bool = True


class CartesiaKeyRequest(BaseModel):
    api_key: str = ""


class CartesiaVoiceRequest(BaseModel):
    voice_id: str = ""


logger = logging.getLogger("lexa.voice")
router = APIRouter(prefix="/voice", tags=["voice"])

TEMP_DIR = Path(tempfile.gettempdir()) / "lexa_voice"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

_MAX_AUDIO_SIZE = 25 * 1024 * 1024
_UPLOAD_CHUNK_SIZE = 64 * 1024
_ALLOWED_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".webm", ".m4a", ".flac"}
_ALLOWED_AUDIO_CONTENT_TYPES = {
    "audio/flac",
    "audio/m4a",
    "audio/mp3",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/wave",
    "audio/webm",
    "audio/x-m4a",
    "audio/x-wav",
    "audio/vnd.wave",
    "application/ogg",
    "video/webm",
}
_AUDIO_CONTENT_TYPE_EXTS = {
    "audio/flac": ".flac",
    "audio/m4a": ".m4a",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/webm": ".webm",
    "audio/x-m4a": ".m4a",
    "audio/x-wav": ".wav",
    "audio/vnd.wave": ".wav",
    "application/ogg": ".ogg",
    "video/webm": ".webm",
}
_LOCAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'<>|]+|(?<!\S)/(?:Users|home|tmp|var|etc)/[^\s\"'<>|]+)"
)


def _voice_safe_error(value, *, max_chars: int = 220) -> str:
    """Return a compact client-facing voice error without paths or secrets."""
    text = redacted_summary(str(value or ""), max_chars=max_chars)
    text = _LOCAL_PATH_RE.sub("[local-path-redacted]", text)
    return text or "Details wurden lokal protokolliert."


def _voice_safe_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    return [_voice_safe_error(value) for value in values[:10]]


def _normalize_stt_result(result):
    """Return stable STT text plus optional engine metadata."""
    if isinstance(result, dict):
        text = str(result.get("text") or result.get("transcript") or result.get("result") or "").strip()
        metadata = {
            key: value
            for key, value in result.items()
            if key not in {"text", "transcript", "result", "success"}
        }
        return text, metadata
    return str(result or "").strip(), {}


def _audio_content_type(upload: UploadFile) -> str:
    return str(upload.content_type or "").split(";", 1)[0].strip().lower()


def _validated_audio_extension(upload: UploadFile) -> tuple[str, JSONResponse | None]:
    content_type = _audio_content_type(upload)
    ext = Path(str(upload.filename or "")).suffix.lower()

    if ext and ext not in _ALLOWED_AUDIO_EXTS:
        return "", JSONResponse({"error": "Nicht unterstuetztes Audioformat."}, status_code=415)
    if (
        content_type
        and content_type not in _ALLOWED_AUDIO_CONTENT_TYPES
        and not (content_type == "application/octet-stream" and ext)
    ):
        return "", JSONResponse({"error": "Nicht unterstuetzter Audio-MIME-Type."}, status_code=415)

    if not ext:
        ext = _AUDIO_CONTENT_TYPE_EXTS.get(content_type, ".webm")
    return ext, None


def _device_summary(device) -> dict | None:
    if not isinstance(device, dict):
        return None
    index = device.get("index")
    return {
        "name": str(device.get("name") or ""),
        "index": int(index) if index is not None else None,
        "max_input_channels": int(device.get("max_input_channels") or 0),
        "max_output_channels": int(device.get("max_output_channels") or 0),
        "default_samplerate": float(device.get("default_samplerate") or 0),
    }


def _default_device_summary(default_device):
    if default_device is None:
        return None
    if isinstance(default_device, (str, bytes)):
        return [str(default_device)]
    try:
        values = list(default_device)
    except TypeError:
        values = [default_device]
    payload = []
    for value in values:
        if value is None:
            payload.append(None)
            continue
        try:
            payload.append(int(value))
        except Exception:
            payload.append(str(value))
    return payload


def _voice_audio_status(probe_audio: bool = False) -> dict:
    try:
        import sounddevice as sd
    except Exception as e:
        return {
            "available": False,
            "input": None,
            "output": None,
            "default_device": None,
            "probe": {"ok": False, "skipped": True},
            "error": f"sounddevice unavailable: {_voice_safe_error(e)}",
        }

    try:
        input_device = _device_summary(sd.query_devices(kind="input"))
    except Exception as e:
        input_device = None
        input_error = _voice_safe_error(e)
    else:
        input_error = ""

    try:
        output_device = _device_summary(sd.query_devices(kind="output"))
    except Exception as e:
        output_device = None
        output_error = _voice_safe_error(e)
    else:
        output_error = ""

    payload = {
        "available": bool(input_device),
        "input": input_device,
        "output": output_device,
        "default_device": _default_device_summary(getattr(getattr(sd, "default", None), "device", None)),
        "probe": {"ok": False, "skipped": not probe_audio},
        "error": input_error or output_error,
    }

    if not probe_audio or not input_device:
        return payload

    try:
        import numpy as np
        from voice.config import SAMPLE_RATE

        start = _time.time()
        audio = sd.rec(int(SAMPLE_RATE * 0.2), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        sd.wait()
        flat = audio.flatten()
        rms = float(np.sqrt(np.mean(flat ** 2))) if len(flat) else 0.0
        payload["probe"] = {
            "ok": True,
            "skipped": False,
            "elapsed_ms": int((_time.time() - start) * 1000),
            "rms": round(rms, 6),
        }
    except Exception as e:
        error = _voice_safe_error(e)
        payload["probe"] = {"ok": False, "skipped": False, "error": error}
        payload["error"] = error
    return payload


def _ready_from_status(status: dict, *keys: str) -> bool:
    if not isinstance(status, dict):
        return False
    for key in keys:
        if key in status:
            return bool(status.get(key))
    return False


async def _build_voice_diagnostics(probe_audio: bool = False) -> dict:
    try:
        from voice.stt import get_stt_status
        stt = await asyncio.to_thread(get_stt_status)
    except Exception as e:
        stt = {"ready": False, "available": False, "error": _voice_safe_error(e)}

    try:
        from voice.tts import get_tts_status
        tts_raw = await asyncio.to_thread(get_tts_status)
        tts = {"tts": tts_raw, **tts_raw}
    except Exception as e:
        tts = {"ready": False, "available": False, "error": _voice_safe_error(e)}

    wake = _wakeword_status_payload(_wake_detector)
    audio = await asyncio.to_thread(_voice_audio_status, probe_audio)
    try:
        from voice.realtime import get_realtime_session_preflight
        realtime_preflight = await asyncio.to_thread(get_realtime_session_preflight)
        realtime = realtime_preflight.get("status") if isinstance(realtime_preflight, dict) else {}
        if not isinstance(realtime, dict):
            realtime = {}
    except Exception as e:
        error = _voice_safe_error(e)
        realtime = {"ready": False, "error": error}
        realtime_preflight = {
            "ok": False,
            "can_start": False,
            "blockers": [error],
            "warnings": [],
            "next_action": "Realtime preflight failed.",
        }

    audio_ok = bool(audio.get("available") and audio.get("input"))
    stt_ok = _ready_from_status(stt, "ready", "available", "deepgram_available", "groq_available", "local_available")
    tts_ok = _ready_from_status(tts, "ready", "available", "elevenlabs_available", "cartesia_available", "sapi_available")
    wake_error = bool(wake.get("error"))
    wake_active = bool(wake.get("active") and wake.get("ready") and wake.get("thread_alive"))
    wake_engine = wake.get("wake_engine") if isinstance(wake.get("wake_engine"), dict) else {}
    wake_engine_name = wake_engine.get("name") or "unknown"
    realtime_blockers = realtime_preflight.get("blockers") if isinstance(realtime_preflight, dict) else []
    realtime_warnings = realtime_preflight.get("warnings") if isinstance(realtime_preflight, dict) else []
    realtime_blockers = _voice_safe_list(realtime_blockers)
    realtime_warnings = _voice_safe_list(realtime_warnings)
    if isinstance(realtime_preflight, dict):
        realtime_preflight = {
            **realtime_preflight,
            "blockers": realtime_blockers,
            "warnings": realtime_warnings,
        }
    realtime_reason = ""
    if realtime_blockers:
        realtime_reason = f" Blocker: {realtime_blockers[0]}"
    elif realtime_warnings:
        realtime_reason = f" Warning: {realtime_warnings[0]}"

    checks = [
        {
            "id": "audio-input",
            "label": "Audio input",
            "state": "ok" if audio_ok else "blocked",
            "detail": audio.get("input", {}).get("name") if audio_ok else (audio.get("error") or "No input device available."),
        },
        {
            "id": "stt",
            "label": "Speech-to-text",
            "state": "ok" if stt_ok else "blocked",
            "detail": f"Engine: {stt.get('engine', 'unknown')}" if stt_ok else (stt.get("error") or "STT unavailable."),
        },
        {
            "id": "tts",
            "label": "Text-to-speech",
            "state": "ok" if tts_ok else "blocked",
            "detail": f"Engine: {tts.get('engine', 'unknown')}" if tts_ok else (tts.get("error") or "TTS unavailable."),
        },
        {
            "id": "wakeword",
            "label": "Wake word",
            "state": "blocked" if wake_error else ("ok" if wake_active else "warn"),
            "detail": wake.get("error") if wake_error else (
                f"Active via {wake_engine_name}." if wake_active else f"Inactive. Engine: {wake_engine_name}."
            ),
        },
        {
            "id": "realtime-voice",
            "label": "Realtime voice",
            "state": "ok",
            "detail": (
                f"{realtime.get('active_path')} active."
                if realtime.get("ready")
                else (
                    f"{realtime.get('preferred')} configured; cascaded fallback is active.{realtime_reason}"
                    if realtime.get("configured")
                    else f"Realtime provider not configured; cascaded fallback is active.{realtime_reason}"
                )
            ),
        },
    ]

    if probe_audio:
        probe = audio.get("probe") or {}
        checks.append({
            "id": "audio-probe",
            "label": "Audio probe",
            "state": "ok" if probe.get("ok") else "blocked",
            "detail": f"{probe.get('elapsed_ms')}ms, rms={probe.get('rms')}" if probe.get("ok") else (probe.get("error") or "Probe failed."),
        })

    if any(check["state"] == "blocked" for check in checks):
        state = "blocked"
    elif any(check["state"] == "warn" for check in checks):
        state = "attention"
    else:
        state = "ready"

    if state == "ready":
        next_action = "Voice stack is ready."
    elif state == "attention" and not wake_active and not wake_error:
        next_action = "Enable Wake Word for hands-free listening."
    elif state == "attention":
        next_action = "Review voice diagnostics warnings."
    else:
        next_action = "Fix blocked voice diagnostics before using voice mode."

    return {
        "ok": state != "blocked",
        "state": state,
        "summary": {
            "ready": "Voice stack is ready.",
            "attention": "Voice stack is usable but needs attention.",
            "blocked": "Voice stack has a blocking issue.",
        }[state],
        "checks": checks,
        "audio": audio,
        "stt": stt,
        "tts": tts,
        "wakeword": wake,
        "realtime": realtime,
        "realtime_preflight": realtime_preflight,
        "nextAction": next_action,
    }


# ═══════════════════════════════════════════════════
#  WEBSOCKET — Real-time voice events
# ═══════════════════════════════════════════════════

@router.websocket("/ws")
async def voice_websocket(websocket: WebSocket):
    """WebSocket for real-time voice events. Connect: ws://127.0.0.1:8000/voice/ws"""
    await websocket.accept()
    client_id, queue = register_ws_client()

    async def _consume():
        while True:
            event = await queue.get()
            await websocket.send_json(event)

    async def _heartbeat():
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping", "ts": _time.time()})

    tasks = [asyncio.ensure_future(_consume()), asyncio.ensure_future(_heartbeat())]
    try:
        await asyncio.gather(*tasks)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[VoiceWS] Client {client_id} error: {e}")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        unregister_ws_client(client_id)


# ═══════════════════════════════════════════════════
#  STT ENDPOINTS
# ═══════════════════════════════════════════════════

@router.get("/diagnostics")
async def voice_diagnostics(probeAudio: bool = Query(default=False)):
    return await _build_voice_diagnostics(probe_audio=probeAudio)


@router.get("/status")
async def voice_status(probeAudio: bool = Query(default=False)):
    return await _build_voice_diagnostics(probe_audio=probeAudio)


@router.get("/architecture")
async def voice_architecture():
    from voice.realtime import get_realtime_voice_status
    from voice.wakeword_engines import get_wakeword_engine_capabilities

    return {
        "version": "voice-stack-v3",
        "wakeword": await asyncio.to_thread(get_wakeword_engine_capabilities),
        "realtime": await asyncio.to_thread(get_realtime_voice_status),
        "active_wakeword": _wakeword_status_payload(_wake_detector).get("wake_engine"),
    }


@router.get("/realtime/preflight")
async def voice_realtime_preflight():
    from voice.realtime import get_realtime_session_preflight

    return await asyncio.to_thread(get_realtime_session_preflight)


@router.post("/realtime/start")
async def voice_realtime_start():
    from voice.realtime import get_realtime_session_preflight

    preflight = await asyncio.to_thread(get_realtime_session_preflight)
    payload = dict(preflight) if isinstance(preflight, dict) else {
        "ok": False,
        "can_start": False,
        "blockers": ["Realtime preflight returned an invalid payload."],
        "warnings": [],
    }

    if not payload.get("can_start"):
        payload["ok"] = False
        payload["session_state"] = "blocked"
        return JSONResponse(payload, status_code=409)

    blockers = list(payload.get("blockers") or [])
    blockers.append("Realtime session manager is not wired to the API endpoint yet.")
    payload.update({
        "ok": False,
        "can_start": False,
        "session_state": "not_started",
        "blockers": blockers,
        "next_action": "Wire the realtime session manager before starting realtime sessions.",
    })
    return JSONResponse(payload, status_code=501)


@router.post("/realtime/stop")
async def voice_realtime_stop():
    from voice.realtime import get_realtime_voice_status

    status = await asyncio.to_thread(get_realtime_voice_status)
    return {
        "ok": True,
        "session_state": "stopped",
        "active": False,
        "provider": status.get("preferred") if isinstance(status, dict) else None,
        "active_path": status.get("active_path") if isinstance(status, dict) else "cascaded_stt_llm_tts",
        "runtime_active": bool(status.get("runtime_active")) if isinstance(status, dict) else False,
    }


@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """Convert uploaded audio to text."""
    if not check_rate_limit("voice"):
        return JSONResponse({"error": "Rate limit erreicht."}, status_code=429)

    ext, error = _validated_audio_extension(audio)
    if error is not None:
        return error
    audio_path = TEMP_DIR / f"stt_{_uuid.uuid4().hex[:12]}{ext}"

    try:
        total_size = 0
        read_start = _time.time()
        with open(audio_path, "wb") as f:
            while True:
                if _time.time() - read_start > 30:
                    return JSONResponse({"error": "Audio-Upload Timeout."}, status_code=408)
                chunk = await audio.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > _MAX_AUDIO_SIZE:
                    return JSONResponse({"error": "Audiodatei zu gross."}, status_code=413)
                f.write(chunk)

        from voice.stt import transcribe_file
        raw_result = await asyncio.to_thread(transcribe_file, str(audio_path))
        text, metadata = _normalize_stt_result(raw_result)
        language = re.sub(r"[^A-Za-z0-9_-]+", "", str(metadata.get("language") or ""))[:16]
        audit_log("stt", "transcribed", f"success={bool(text)} textChars={len(text)} language={language}")
        payload = {"text": text, "success": bool(text), **metadata}
        if not text and "error" not in payload:
            payload["error"] = "Keine Sprache erkannt."
        return payload
    except Exception as e:
        logger.error(f"STT error: {e}", exc_info=True)
        return JSONResponse({"text": "", "success": False, "error": "STT fehlgeschlagen."}, status_code=500)
    finally:
        audio_path.unlink(missing_ok=True)


@router.get("/stt/status")
async def stt_status():
    from voice.stt import get_stt_status
    return await asyncio.to_thread(get_stt_status)


@router.get("/stt/models")
async def stt_models():
    from voice.stt import get_available_models
    return {"models": await asyncio.to_thread(get_available_models)}


@router.post("/stt/model")
async def stt_set_model(data: STTModelRequest):
    from voice.stt import set_model_size
    return await asyncio.to_thread(set_model_size, data.model)


@router.post("/stt/language")
async def stt_set_language(data: STTLanguageRequest):
    from voice.stt import set_language
    result = await asyncio.to_thread(set_language, data.language)
    if result.get("success"):
        audit_log("stt", "language_changed", f"lang={data.language}")
    return result


@router.post("/stt/engine")
async def stt_set_engine(data: STTEngineRequest):
    from voice.stt import set_engine
    result = await asyncio.to_thread(set_engine, data.engine)
    if result.get("success"):
        audit_log("stt", "engine_changed", f"engine={data.engine}")
    return result


# ── Deepgram API Key ─────────────────────

@router.post("/stt/deepgram/key")
async def deepgram_set_key(data: DeepgramKeyRequest):
    if not data.api_key or not data.api_key.strip():
        return JSONResponse({"error": "API-Key darf nicht leer sein."}, status_code=400)
    from voice.stt import set_deepgram_key
    result = await asyncio.to_thread(set_deepgram_key, data.api_key)
    if result.get("success"):
        audit_log("stt", "deepgram_key_set", "Key updated")
    return result


@router.delete("/stt/deepgram/key")
async def deepgram_delete_key():
    from voice.stt import delete_deepgram_key
    result = await asyncio.to_thread(delete_deepgram_key)
    if result.get("success"):
        audit_log("stt", "deepgram_key_deleted", "Key removed")
    return result


# ═══════════════════════════════════════════════════
#  TTS ENDPOINTS
# ═══════════════════════════════════════════════════

@router.post("/tts")
async def text_to_speech(data: TTSRequest):
    """Convert text to speech. Returns audio file."""
    if not check_rate_limit("voice"):
        return JSONResponse({"error": "Rate limit erreicht."}, status_code=429)
    text = str(data.text or "").strip()
    if not text:
        return JSONResponse({"error": "Kein Text angegeben."}, status_code=400)
    if len(text) > MAX_TTS_TEXT_CHARS:
        return JSONResponse({"error": f"Text ist zu lang (max {MAX_TTS_TEXT_CHARS} Zeichen)."}, status_code=413)

    try:
        from voice.tts import speak_async
        audio_path = await speak_async(text)
        audit_log("tts", "generated", f"textChars={len(text)}")
        is_mp3 = audio_path.endswith(".mp3")
        return FileResponse(
            audio_path,
            media_type="audio/mpeg" if is_mp3 else "audio/wav",
            filename="lexa_response.mp3" if is_mp3 else "lexa_response.wav",
        )
    except Exception as e:
        logger.error(f"TTS error: {e}", exc_info=True)
        return JSONResponse({"error": t("error.ttsError")}, status_code=500)


@router.get("/tts/status")
async def tts_status():
    from voice.tts import get_tts_status
    status = await asyncio.to_thread(get_tts_status)
    return {"tts": status, **status}


@router.get("/tts/voices")
async def tts_voices():
    from voice.tts import get_elevenlabs_voices
    voices = await asyncio.to_thread(get_elevenlabs_voices)
    return {"voices": voices}


# ── Cartesia API Key ─────────────────────

@router.post("/tts/cartesia/key")
async def cartesia_set_key(data: CartesiaKeyRequest):
    if not data.api_key or not data.api_key.strip():
        return JSONResponse({"error": "API-Key darf nicht leer sein."}, status_code=400)
    from voice.tts import set_cartesia_key
    result = await asyncio.to_thread(set_cartesia_key, data.api_key)
    if result.get("success"):
        audit_log("tts", "cartesia_key_set", "Key updated")
    return result


@router.delete("/tts/cartesia/key")
async def cartesia_delete_key():
    from voice.tts import delete_cartesia_key
    result = await asyncio.to_thread(delete_cartesia_key)
    return result


@router.post("/tts/cartesia/voice")
async def cartesia_set_voice(data: CartesiaVoiceRequest):
    if not data.voice_id or not data.voice_id.strip():
        return JSONResponse({"error": "Voice-ID darf nicht leer sein."}, status_code=400)
    from voice.tts import set_cartesia_voice
    result = await asyncio.to_thread(set_cartesia_voice, data.voice_id)
    if not result.get("success", False):
        return JSONResponse({"error": result.get("error", "Voice-ID konnte nicht gesetzt werden.")}, status_code=400)
    return result


# ── ElevenLabs API Key ───────────────────

@router.post("/tts/elevenlabs/key")
async def elevenlabs_set_key(data: ElevenLabsKeyRequest):
    if not data.api_key or not data.api_key.strip():
        return JSONResponse({"error": "API-Key darf nicht leer sein."}, status_code=400)
    from voice.tts import set_elevenlabs_key
    result = await asyncio.to_thread(set_elevenlabs_key, data.api_key)
    if result.get("success"):
        audit_log("tts", "elevenlabs_key_set", "Key updated")
    return result


@router.delete("/tts/elevenlabs/key")
async def elevenlabs_delete_key():
    from voice.tts import delete_elevenlabs_key
    result = await asyncio.to_thread(delete_elevenlabs_key)
    return result


@router.get("/tts/elevenlabs/voices")
async def elevenlabs_voices():
    from voice.tts import get_elevenlabs_voices
    return {"voices": await asyncio.to_thread(get_elevenlabs_voices)}


@router.post("/tts/elevenlabs/voice")
async def elevenlabs_set_voice(data: ElevenLabsVoiceRequest):
    if not data.voice_id or not data.voice_id.strip():
        return JSONResponse({"error": "Voice-ID darf nicht leer sein."}, status_code=400)
    from voice.tts import set_elevenlabs_voice
    result = await asyncio.to_thread(set_elevenlabs_voice, data.voice_id)
    if not result.get("success", False):
        return JSONResponse({"error": result.get("error", "Voice-ID konnte nicht gesetzt werden.")}, status_code=400)
    return result


@router.post("/tts/elevenlabs/model")
async def elevenlabs_set_model(data: ElevenLabsModelRequest):
    from voice.tts import set_elevenlabs_model
    result = await asyncio.to_thread(set_elevenlabs_model, data.model)
    if not result.get("success", False):
        return JSONResponse({"error": result.get("error", "Modell konnte nicht gesetzt werden.")}, status_code=400)
    return result


@router.post("/tts/elevenlabs/settings")
async def elevenlabs_set_settings(data: ElevenLabsSettingsRequest):
    from voice.tts import set_elevenlabs_settings
    return await asyncio.to_thread(set_elevenlabs_settings, data.stability, data.similarity, data.style)


@router.post("/tts/elevenlabs/toggle")
async def elevenlabs_toggle(data: ElevenLabsToggleRequest):
    from voice.tts import set_elevenlabs_enabled
    result = await asyncio.to_thread(set_elevenlabs_enabled, data.enabled)
    if result.get("success"):
        audit_log("tts", "elevenlabs_toggled", f"enabled={data.enabled}")
    return result


# ═══════════════════════════════════════════════════
#  WAKE WORD + CONVERSATION MODE
# ═══════════════════════════════════════════════════

_wake_detector = None
_detector_lock = threading.Lock()
_STOP_TIMEOUT = 5.0

_last_poll_times: dict[str, float] = {}
_MAX_POLL_CLIENTS = 100
_POLL_MIN_INTERVAL = 0.1
_WAKEWORD_STARTUP_TIMEOUT = 6.0


def _wakeword_default_status() -> dict:
    configured_engine = WAKE_ENGINE or "openwakeword"
    return {
        "active": False,
        "ready": False,
        "in_conversation": False,
        "phrases": list(WAKE_PHRASES),
        "sensitivity": _DEFAULT_WAKE_SENSITIVITY,
        "thread_alive": False,
        "error": "",
        "last_transcript": "",
        "last_detected_text": "",
        "last_command": "",
        "last_command_source": "",
        "last_window_rms": 0.0,
        "wake_checks": 0,
        "stt_checks": 0,
        "skipped_stt_checks": 0,
        "fallback_stt_min_interval_s": float(WAKE_FALLBACK_STT_MIN_INTERVAL_S),
        "fallback_stt_max_interval_s": float(WAKE_FALLBACK_STT_MAX_INTERVAL_S),
        "fallback_stt_backoff_step_s": float(WAKE_FALLBACK_STT_BACKOFF_STEP_S),
        "fallback_stt_interval_s": float(WAKE_FALLBACK_STT_MIN_INTERVAL_S),
        "non_wake_transcripts": 0,
        "last_heard_at": 0.0,
        "last_detected_at": 0.0,
        "wake_engine": {
            "name": configured_engine,
            "ready": False,
            "local": configured_engine in {"openwakeword", "local", "auto", "porcupine"},
            "uses_stt": False,
            "legacy": False,
            "configured_mode": configured_engine,
            "model_refs": [part.strip() for part in str(WAKE_OPENWAKEWORD_MODELS or "").split(",") if part.strip()],
            "threshold": float(WAKE_OPENWAKEWORD_THRESHOLD),
            "patience": int(WAKE_OPENWAKEWORD_PATIENCE),
            "vad_threshold": float(WAKE_OPENWAKEWORD_VAD_THRESHOLD),
            "auto_download": bool(WAKE_OPENWAKEWORD_AUTO_DOWNLOAD),
            "detail": "Local wake-word engine is configured but not running.",
        },
    }


def _wakeword_status_payload(detector) -> dict:
    if not detector:
        return _wakeword_default_status()
    status = getattr(detector, "status", None)
    if callable(status):
        status = status()
    if not isinstance(status, dict):
        status = {}
    payload = {**_wakeword_default_status(), **status}
    for key in ("sensitivity", "last_window_rms", "last_heard_at", "last_detected_at",
                "fallback_stt_min_interval_s", "fallback_stt_max_interval_s",
                "fallback_stt_backoff_step_s", "fallback_stt_interval_s"):
        try:
            payload[key] = float(payload.get(key) or 0.0)
        except Exception:
            payload[key] = 0.0
    for key in ("wake_checks", "stt_checks", "skipped_stt_checks", "non_wake_transcripts"):
        try:
            payload[key] = int(payload.get(key) or 0)
        except Exception:
            payload[key] = 0
    if payload.get("error"):
        payload["error"] = _voice_safe_error(payload.get("error"))
    for key in ("last_transcript", "last_detected_text", "last_command"):
        value = str(payload.get(key) or "")
        if value:
            payload[f"{key}_chars"] = len(value)
            payload[key] = "[redacted]"
    wake_engine = payload.get("wake_engine")
    if isinstance(wake_engine, dict) and wake_engine.get("detail"):
        payload["wake_engine"] = {**wake_engine, "detail": _voice_safe_error(wake_engine.get("detail"))}
    return payload


def _on_wake():
    push_event("wake")
    push_event("conversation_start")
    logger.info("[WakeWord] Wake word heard")


def _on_conversation_state(state: str):
    push_state(state)


def _on_volume(vol: float):
    push_volume(vol)


def _on_chat_turn(command_text: str, conversation_history: list = None):
    """Conversation turn callback — delegates to ConversationEngine."""
    from voice.conversation import ConversationEngine
    engine = ConversationEngine(
        on_state=_on_conversation_state,
        on_volume=_on_volume,
    )
    return engine.run_single_turn(command_text, conversation_history=conversation_history)


def _create_detector(*, streaming: bool = True):
    from voice.wakeword import WakeWordDetector

    detector = WakeWordDetector(
        on_command=None,
        on_wake=_on_wake,
        on_chat=_on_chat_turn,
    )
    detector._on_conversation_state = _on_conversation_state
    detector._on_volume = _on_volume
    return detector


async def _stop_detector_with_timeout(detector, timeout: float = _STOP_TIMEOUT):
    try:
        await asyncio.wait_for(asyncio.to_thread(detector.stop), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"[WakeWord] Stop timed out after {timeout}s")
        try:
            detector.is_listening = False
        except Exception:
            pass


@router.post("/wakeword/start")
async def wakeword_start():
    global _wake_detector
    with _detector_lock:
        if _wake_detector and getattr(_wake_detector, "is_listening", False):
            return {"status": "already_running", **_wakeword_status_payload(_wake_detector)}
        try:
            _wake_detector = _create_detector(streaming=True)
            _wake_detector.start(wait_ready_s=_WAKEWORD_STARTUP_TIMEOUT)
            status = _wakeword_status_payload(_wake_detector)
            if not status.get("active") or not status.get("ready"):
                error = status.get("error") or "Wake-Word-Detektor ist nicht bereit."
                try:
                    _wake_detector.stop()
                except Exception:
                    pass
                _wake_detector = None
                return JSONResponse(
                    {"status": "failed", "active": False, "ready": False, "error": error},
                    status_code=503,
                )
            return {"status": "started", "conversation_mode": True, "streaming": True, **status}
        except Exception as e:
            logger.error(f"Wake word start failed: {e}", exc_info=True)
            _wake_detector = None
            return JSONResponse({"error": "Wake-Word-Detektor konnte nicht gestartet werden."}, status_code=500)


@router.post("/wakeword/stop")
async def wakeword_stop():
    global _wake_detector
    if _wake_detector:
        await _stop_detector_with_timeout(_wake_detector)
        _wake_detector = None
    return {"status": "stopped"}


@router.get("/wakeword/status")
async def wakeword_status():
    return _wakeword_status_payload(_wake_detector)


@router.get("/wakeword/events")
async def wakeword_events(client_id: str = "default"):
    """HTTP polling fallback for wake word events."""
    now = _time.time()
    # client_id auf sicheres Format/Laenge begrenzen, um unbegrenztes Dict-Wachstum
    # ueber zufaellige IDs zu verhindern.
    client_id = re.sub(r"[^A-Za-z0-9_-]+", "", str(client_id or ""))[:64] or "default"
    # Bereinigung bei jedem Aufruf: veraltete Eintraege entfernen, danach hartes Limit erzwingen.
    cutoff = now - 300
    stale = [k for k, v in _last_poll_times.items() if v < cutoff]
    for k in stale:
        _last_poll_times.pop(k, None)
    last = _last_poll_times.get(client_id, 0.0)
    if now - last < _POLL_MIN_INTERVAL:
        return {"events": [], "throttled": True}
    if client_id not in _last_poll_times and len(_last_poll_times) >= _MAX_POLL_CLIENTS:
        # Aeltesten Eintrag verdraengen, damit das Gesamtlimit nie ueberschritten wird.
        oldest = min(_last_poll_times, key=_last_poll_times.get)
        _last_poll_times.pop(oldest, None)
    _last_poll_times[client_id] = now
    return {"events": pop_fallback_events()}


@router.get("/wakeword/sensitivity")
async def wakeword_get_sensitivity():
    if _wake_detector and hasattr(_wake_detector, "sensitivity"):
        return {"sensitivity": _wake_detector.sensitivity}
    return {"sensitivity": _DEFAULT_WAKE_SENSITIVITY}


@router.post("/wakeword/sensitivity")
async def wakeword_set_sensitivity(data: SensitivityRequest):
    value = data.sensitivity
    if not (0.001 <= value <= 1.0):
        return JSONResponse({"error": "Sensitivity muss zwischen 0.001 und 1.0 liegen."}, status_code=400)
    if _wake_detector and hasattr(_wake_detector, "sensitivity"):
        _wake_detector.sensitivity = value
        audit_log("wakeword", "sensitivity_changed", f"sensitivity={value}")
        return {"success": True, "sensitivity": value}
    return JSONResponse({"error": "Wake-Word-Detektor nicht aktiv."}, status_code=409)


@router.post("/conversation/start")
async def conversation_start():
    """Start direct conversation — skip wake word, immediately listen."""
    global _wake_detector
    with _detector_lock:
        if _wake_detector and getattr(_wake_detector, "is_listening", False):
            await _stop_detector_with_timeout(_wake_detector)
            _wake_detector = None
        try:
            _wake_detector = _create_detector(streaming=True)
            _wake_detector.start_direct(wait_ready_s=_WAKEWORD_STARTUP_TIMEOUT)
            status = _wakeword_status_payload(_wake_detector)
            if not status.get("active") or not status.get("ready"):
                error = status.get("error") or "Konversationsmodus ist nicht bereit."
                try:
                    _wake_detector.stop()
                except Exception:
                    pass
                _wake_detector = None
                return JSONResponse(
                    {"status": "failed", "active": False, "ready": False, "error": error},
                    status_code=503,
                )
            return {"status": "started", "mode": "direct_conversation", "streaming": True, **status}
        except Exception as e:
            logger.error(f"Conversation start failed: {e}", exc_info=True)
            _wake_detector = None
            return JSONResponse({"error": "Konversationsmodus konnte nicht gestartet werden."}, status_code=500)


@router.post("/conversation/stop")
async def conversation_stop():
    global _wake_detector
    if _wake_detector:
        await _stop_detector_with_timeout(_wake_detector)
        _wake_detector = None
    return {"status": "stopped"}

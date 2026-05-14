"""Lexa AI — Voice Router v3
Thin API layer for STT, TTS, Wake Word + Conversation Mode.
All conversation logic lives in voice/conversation.py.
"""

import asyncio
import logging
import tempfile
import threading
import time as _time
import uuid as _uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.security import check_rate_limit, audit_log
from backend.i18n import t
from backend.voice_ws import (
    push_event, push_volume, push_state, push_command,
    push_response, push_response_chunk, push_error,
    pop_fallback_events, register_ws_client, unregister_ws_client,
)

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
    sensitivity: float = 0.015

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
TEMP_DIR.mkdir(exist_ok=True)

_MAX_AUDIO_SIZE = 25 * 1024 * 1024
_UPLOAD_CHUNK_SIZE = 64 * 1024


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

    try:
        await asyncio.gather(_consume(), _heartbeat())
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[VoiceWS] Client {client_id} error: {e}")
    finally:
        unregister_ws_client(client_id)


# ═══════════════════════════════════════════════════
#  STT ENDPOINTS
# ═══════════════════════════════════════════════════

@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """Convert uploaded audio to text."""
    if not check_rate_limit("voice"):
        return JSONResponse({"error": "Rate limit erreicht."}, status_code=429)

    ext = Path(audio.filename).suffix.lower() if audio.filename else ".webm"
    ext = ext if ext in (".wav", ".mp3", ".ogg", ".webm", ".m4a", ".flac") else ".webm"
    audio_path = TEMP_DIR / f"stt_{_uuid.uuid4().hex[:12]}{ext}"

    try:
        total_size = 0
        read_start = _time.time()
        with open(audio_path, "wb") as f:
            while True:
                if _time.time() - read_start > 30:
                    audio_path.unlink(missing_ok=True)
                    return JSONResponse({"error": "Audio-Upload Timeout."}, status_code=408)
                chunk = await audio.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > _MAX_AUDIO_SIZE:
                    audio_path.unlink(missing_ok=True)
                    return JSONResponse({"error": "Audiodatei zu gross."}, status_code=413)
                f.write(chunk)

        from voice.stt import transcribe_file
        text = await asyncio.to_thread(transcribe_file, str(audio_path))
        audit_log("stt", "transcribed", f"text={text[:80]}")
        return {"text": text, "success": True}
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
    if not data.text:
        return JSONResponse({"error": "Kein Text angegeben."}, status_code=400)
    if not check_rate_limit("voice"):
        return JSONResponse({"error": "Rate limit erreicht."}, status_code=429)

    try:
        from voice.tts import speak_async
        audio_path = await speak_async(data.text)
        audit_log("tts", "generated", f"text={data.text[:50]}")
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
        if _wake_detector and _wake_detector.is_listening:
            return {"status": "already_running"}
        try:
            _wake_detector = _create_detector(streaming=True)
            _wake_detector.start()
            return {"status": "started", "conversation_mode": True, "streaming": True}
        except Exception as e:
            logger.error(f"Wake word start failed: {e}", exc_info=True)
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
    if _wake_detector:
        return _wake_detector.status
    return {"active": False, "in_conversation": False, "phrases": ["lexa"], "sensitivity": 0.015}


@router.get("/wakeword/events")
async def wakeword_events(client_id: str = "default"):
    """HTTP polling fallback for wake word events."""
    now = _time.time()
    last = _last_poll_times.get(client_id, 0.0)
    if now - last < _POLL_MIN_INTERVAL:
        return {"events": [], "throttled": True}
    _last_poll_times[client_id] = now
    if len(_last_poll_times) > _MAX_POLL_CLIENTS:
        cutoff = now - 300
        stale = [k for k, v in _last_poll_times.items() if v < cutoff]
        for k in stale:
            _last_poll_times.pop(k, None)
    return {"events": pop_fallback_events()}


@router.get("/wakeword/sensitivity")
async def wakeword_get_sensitivity():
    if _wake_detector and hasattr(_wake_detector, "sensitivity"):
        return {"sensitivity": _wake_detector.sensitivity}
    return {"sensitivity": 0.015}


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
        if _wake_detector and _wake_detector.is_listening:
            await _stop_detector_with_timeout(_wake_detector)
            _wake_detector = None
        try:
            _wake_detector = _create_detector(streaming=True)
            _wake_detector.start_direct()
            return {"status": "started", "mode": "direct_conversation", "streaming": True}
        except Exception as e:
            logger.error(f"Conversation start failed: {e}", exc_info=True)
            return JSONResponse({"error": "Konversationsmodus konnte nicht gestartet werden."}, status_code=500)


@router.post("/conversation/stop")
async def conversation_stop():
    global _wake_detector
    if _wake_detector:
        await _stop_detector_with_timeout(_wake_detector)
        _wake_detector = None
    return {"status": "stopped"}

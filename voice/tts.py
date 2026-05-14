"""Lexa AI — Text-to-Speech v2 (Cartesia Sonic + ElevenLabs + SAPI)

Primary: Cartesia Sonic 2 (HTTP, ~90ms TTFB, cheap)
Fallback: ElevenLabs Turbo v2.5 (HTTP streaming, ~75ms, best quality)
Offline: Windows SAPI via pyttsx3

Audio caching by content hash prevents re-generation.
Text chunking at sentence boundaries for long responses.
"""

import os
import re
import json
import logging
import hashlib
import asyncio
import requests
from pathlib import Path

from voice.config import (
    AUDIO_CACHE_DIR,
    CARTESIA_API_URL, CARTESIA_MODEL, CARTESIA_VOICE_ID, CARTESIA_OUTPUT_FORMAT,
    ELEVENLABS_API_BASE, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL,
    ELEVENLABS_STABILITY, ELEVENLABS_SIMILARITY, ELEVENLABS_STYLE,
    MAX_TTS_CHUNK_CHARS, MAX_TTS_TEXT_CHARS,
)

logger = logging.getLogger("lexa.tts")

# ═══════════════════════════════════════════════════
#  API KEY MANAGEMENT
# ═══════════════════════════════════════════════════

_keys: dict[str, str | None] = {"cartesia": None, "elevenlabs": None}
_keys_loaded: dict[str, bool] = {"cartesia": False, "elevenlabs": False}

# Persistent HTTP sessions
_sessions: dict[str, requests.Session] = {
    "cartesia": requests.Session(),
    "elevenlabs": requests.Session(),
}
_sessions["elevenlabs"].headers.update({
    "Content-Type": "application/json",
    "Accept": "audio/mpeg",
})


def _get_key(provider: str) -> str | None:
    if _keys_loaded[provider] and _keys[provider] is not None:
        return _keys[provider]
    try:
        import keyring
        key_names = {
            "cartesia": "cartesia_api_key",
            "elevenlabs": "elevenlabs_api_key",
        }
        _keys[provider] = keyring.get_password("lexa-ai", key_names[provider])
    except Exception:
        _keys[provider] = None
    _keys_loaded[provider] = _keys[provider] is not None
    if _keys[provider] and provider == "elevenlabs":
        _sessions["elevenlabs"].headers["xi-api-key"] = _keys[provider]
    return _keys[provider]


# ═══════════════════════════════════════════════════
#  MUTABLE CONFIG
# ═══════════════════════════════════════════════════

_cartesia_voice_id = CARTESIA_VOICE_ID
_cartesia_model = CARTESIA_MODEL
_elevenlabs_voice_id = ELEVENLABS_VOICE_ID
_elevenlabs_model = ELEVENLABS_MODEL
_elevenlabs_stability = ELEVENLABS_STABILITY
_elevenlabs_similarity = ELEVENLABS_SIMILARITY
_elevenlabs_style = ELEVENLABS_STYLE
_elevenlabs_enabled = True

# Sentence split pattern
_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')

# ═══════════════════════════════════════════════════
#  TEXT CHUNKING
# ═══════════════════════════════════════════════════

def _chunk_text(text: str, max_chars: int = MAX_TTS_CHUNK_CHARS) -> list[str]:
    """Split long text into chunks at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    sentences = _SENTENCE_SPLIT.split(text)
    current = ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            words = sentence.split()
            word_chunk = ""
            for word in words:
                if len(word_chunk) + len(word) + 1 > max_chars:
                    if word_chunk:
                        chunks.append(word_chunk.strip())
                    word_chunk = word
                else:
                    word_chunk = f"{word_chunk} {word}" if word_chunk else word
            if word_chunk:
                current = word_chunk
            continue

        if len(current) + len(sentence) + 1 > max_chars:
            if current:
                chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence

    if current.strip():
        chunks.append(current.strip())
    return chunks


# ═══════════════════════════════════════════════════
#  CARTESIA SONIC (Primary — fast, cheap)
# ═══════════════════════════════════════════════════

def _speak_cartesia(text: str, output_path: str) -> str:
    """Generate speech via Cartesia Sonic HTTP API."""
    api_key = _get_key("cartesia")
    if not api_key:
        raise RuntimeError("Cartesia API key not configured")

    payload = {
        "model_id": _cartesia_model,
        "transcript": text[:MAX_TTS_TEXT_CHARS],
        "voice": {"mode": "id", "id": _cartesia_voice_id},
        "output_format": CARTESIA_OUTPUT_FORMAT,
        "language": "de",
    }

    read_timeout = min(30 + len(text) // 100, 120)
    resp = _sessions["cartesia"].post(
        CARTESIA_API_URL,
        headers={
            "X-API-Key": api_key,
            "Cartesia-Version": "2024-06-10",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=(10, read_timeout),
        stream=True,
    )

    if resp.status_code == 200:
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=4096):
                if chunk:
                    f.write(chunk)
        logger.info(f"TTS [Cartesia {_cartesia_model}]: {output_path}")
        return output_path

    error_msg = resp.text[:200] if resp.text else "Unknown error"
    raise RuntimeError(f"Cartesia error {resp.status_code}: {error_msg}")


# ═══════════════════════════════════════════════════
#  ELEVENLABS (Fallback — best quality)
# ═══════════════════════════════════════════════════

def _speak_elevenlabs(text: str, output_path: str) -> str:
    """Generate speech via ElevenLabs streaming API."""
    api_key = _get_key("elevenlabs")
    if not api_key:
        raise RuntimeError("ElevenLabs API key not configured")

    url = f"{ELEVENLABS_API_BASE}/text-to-speech/{_elevenlabs_voice_id}/stream"
    payload = {
        "text": text[:MAX_TTS_TEXT_CHARS],
        "model_id": _elevenlabs_model,
        "voice_settings": {
            "stability": _elevenlabs_stability,
            "similarity_boost": _elevenlabs_similarity,
            "style": _elevenlabs_style,
            "use_speaker_boost": True,
        },
    }

    read_timeout = min(30 + len(text) // 100, 120)
    resp = _sessions["elevenlabs"].post(
        url, json=payload, timeout=(10, read_timeout), stream=True,
    )

    if resp.status_code == 200:
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=2048):
                if chunk:
                    f.write(chunk)
        logger.info(f"TTS [ElevenLabs {_elevenlabs_model}]: {output_path}")
        return output_path

    error_msg = resp.text[:200] if resp.text else "Unknown error"
    raise RuntimeError(f"ElevenLabs error {resp.status_code}: {error_msg}")


# ═══════════════════════════════════════════════════
#  WINDOWS SAPI (Offline fallback)
# ═══════════════════════════════════════════════════

def _speak_sapi(text: str, output_path: str) -> str:
    """Fallback TTS using Windows SAPI (pyttsx3)."""
    try:
        import pyttsx3
        import concurrent.futures

        def _generate():
            engine = pyttsx3.init()
            engine.setProperty("rate", 160)
            engine.setProperty("volume", 0.9)
            for voice in engine.getProperty("voices"):
                if "german" in voice.name.lower() or "de" in voice.id.lower():
                    engine.setProperty("voice", voice.id)
                    break
            engine.save_to_file(text, output_path)
            engine.runAndWait()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(_generate).result(timeout=30)

        if Path(output_path).exists() and Path(output_path).stat().st_size > 0:
            logger.info(f"TTS [SAPI fallback]: {output_path}")
            return output_path
        raise RuntimeError("SAPI produced empty output")
    except ImportError:
        raise RuntimeError("pyttsx3 not installed")
    except Exception as e:
        raise RuntimeError(f"SAPI failed: {e}")


# ═══════════════════════════════════════════════════
#  MP3 CONCATENATION
# ═══════════════════════════════════════════════════

def _concat_mp3_chunks(chunk_paths: list[str], output_path: str):
    """Concatenate MP3 files. Tries pydub → ffmpeg → binary concat."""
    try:
        from pydub import AudioSegment
        combined = AudioSegment.empty()
        for cp in chunk_paths:
            combined += AudioSegment.from_mp3(cp)
        combined.export(output_path, format="mp3", bitrate="128k")
        return
    except (ImportError, Exception):
        pass

    # Binary concat fallback
    with open(output_path, "wb") as out:
        for cp in chunk_paths:
            with open(cp, "rb") as inp:
                out.write(inp.read())


# ═══════════════════════════════════════════════════
#  MAIN SPEAK FUNCTIONS
# ═══════════════════════════════════════════════════

async def speak_async(text: str, output_path: str = "") -> str:
    """Convert text to speech. Returns absolute path to audio file.
    Fallback chain: Cartesia → ElevenLabs → SAPI."""
    if not text or not text.strip():
        raise ValueError("Text darf nicht leer sein.")

    # Include voice ID in cache key so voice changes take effect
    voice_key = _elevenlabs_voice_id if (_elevenlabs_enabled and _get_key("elevenlabs")) else _cartesia_voice_id
    cache_input = f"{text}|{voice_key}".encode()
    text_hash = hashlib.sha256(cache_input).hexdigest()[:24]
    mp3_path = str(AUDIO_CACHE_DIR / f"tts_{text_hash}.mp3")

    # Cache hit
    if Path(mp3_path).exists():
        return mp3_path

    target = output_path or mp3_path
    chunks = _chunk_text(text)

    if len(chunks) == 1:
        return await _speak_single(chunks[0], target)
    else:
        return await _speak_multi(chunks, text_hash, target, text)


async def _speak_single(text: str, target: str) -> str:
    """Single chunk — 3-tier fallback."""
    # Tier 1: ElevenLabs (best quality voice)
    if _elevenlabs_enabled:
        try:
            return await asyncio.to_thread(_speak_elevenlabs, text, target)
        except Exception as e:
            logger.warning(f"ElevenLabs failed: {e}")

    # Tier 2: Cartesia (fast, cheap)
    try:
        return await asyncio.to_thread(_speak_cartesia, text, target)
    except Exception as e:
        logger.warning(f"Cartesia failed: {e}")

    # Tier 3: Windows SAPI (offline)
    sapi_path = target.replace(".mp3", ".wav") if target.endswith(".mp3") else target + ".wav"
    return await asyncio.to_thread(_speak_sapi, text, sapi_path)


async def _speak_multi(chunks: list[str], text_hash: str,
                       target: str, full_text: str) -> str:
    """Multi-chunk — generate each chunk, concatenate."""
    logger.info(f"TTS chunking: {len(chunks)} chunks for {len(full_text)} chars")
    chunk_paths = []
    try:
        for i, chunk in enumerate(chunks):
            chunk_path = str(AUDIO_CACHE_DIR / f"tts_{text_hash}_c{i}.mp3")
            await _speak_single(chunk, chunk_path)
            chunk_paths.append(chunk_path)

        _concat_mp3_chunks(chunk_paths, target)

        for cp in chunk_paths:
            try:
                Path(cp).unlink()
            except OSError:
                pass

        logger.info(f"TTS concatenated {len(chunks)} chunks")
        return target
    except Exception as e:
        for cp in chunk_paths:
            try:
                Path(cp).unlink()
            except OSError:
                pass
        raise


def speak(text: str, output_path: str = "") -> str:
    """Synchronous wrapper for speak_async."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        def _run():
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(speak_async(text, output_path))
            finally:
                new_loop.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run).result(timeout=60)
    else:
        return asyncio.run(speak_async(text, output_path))


# ═══════════════════════════════════════════════════
#  CONFIG MANAGEMENT
# ═══════════════════════════════════════════════════

def set_cartesia_key(api_key: str) -> dict:
    if not api_key or not api_key.strip():
        return {"success": False, "error": "API-Key darf nicht leer sein."}
    try:
        import keyring
        api_key = api_key.strip()
        keyring.set_password("lexa-ai", "cartesia_api_key", api_key)
        _keys["cartesia"] = api_key
        _keys_loaded["cartesia"] = True
        logger.info("Cartesia API key saved")
        clear_cache()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_cartesia_key() -> dict:
    try:
        import keyring
        keyring.delete_password("lexa-ai", "cartesia_api_key")
        _keys["cartesia"] = None
        _keys_loaded["cartesia"] = True
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_cartesia_voice(voice_id: str) -> dict:
    global _cartesia_voice_id
    if not voice_id or not voice_id.strip():
        return {"success": False, "error": "Voice-ID darf nicht leer sein."}
    _cartesia_voice_id = voice_id.strip()
    clear_cache()
    return {"success": True, "voice_id": _cartesia_voice_id}


def set_elevenlabs_key(api_key: str) -> dict:
    if not api_key or not api_key.strip():
        return {"success": False, "error": "API-Key darf nicht leer sein."}
    try:
        import keyring
        api_key = api_key.strip()
        keyring.set_password("lexa-ai", "elevenlabs_api_key", api_key)
        _keys["elevenlabs"] = api_key
        _keys_loaded["elevenlabs"] = True
        _sessions["elevenlabs"].headers["xi-api-key"] = api_key
        logger.info("ElevenLabs API key saved")
        clear_cache()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_elevenlabs_key() -> dict:
    try:
        import keyring
        keyring.delete_password("lexa-ai", "elevenlabs_api_key")
        _keys["elevenlabs"] = None
        _keys_loaded["elevenlabs"] = True
        _sessions["elevenlabs"].headers.pop("xi-api-key", None)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_elevenlabs_voice(voice_id: str) -> dict:
    global _elevenlabs_voice_id
    if not voice_id or not voice_id.strip():
        return {"success": False, "error": "Voice-ID darf nicht leer sein."}
    _elevenlabs_voice_id = voice_id.strip()
    clear_cache()
    return {"success": True, "voice_id": _elevenlabs_voice_id}


def set_elevenlabs_model(model_id: str) -> dict:
    global _elevenlabs_model
    allowed = {"eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_turbo_v2"}
    if model_id not in allowed:
        return {"success": False, "error": f"Unbekanntes Modell: {model_id}"}
    _elevenlabs_model = model_id
    clear_cache()
    return {"success": True, "model": _elevenlabs_model}


def set_elevenlabs_settings(stability: float = None, similarity: float = None,
                            style: float = None) -> dict:
    global _elevenlabs_stability, _elevenlabs_similarity, _elevenlabs_style
    if stability is not None:
        _elevenlabs_stability = max(0.0, min(1.0, stability))
    if similarity is not None:
        _elevenlabs_similarity = max(0.0, min(1.0, similarity))
    if style is not None:
        _elevenlabs_style = max(0.0, min(1.0, style))
    clear_cache()
    return {
        "success": True,
        "stability": _elevenlabs_stability,
        "similarity": _elevenlabs_similarity,
        "style": _elevenlabs_style,
    }


def set_elevenlabs_enabled(enabled: bool) -> dict:
    global _elevenlabs_enabled
    _elevenlabs_enabled = bool(enabled)
    logger.info(f"ElevenLabs TTS {'enabled' if _elevenlabs_enabled else 'disabled'}")
    return {"success": True, "enabled": _elevenlabs_enabled}


def is_elevenlabs_enabled() -> bool:
    return _elevenlabs_enabled


def get_elevenlabs_voices() -> list[dict]:
    api_key = _get_key("elevenlabs")
    if not api_key:
        return []
    try:
        resp = _sessions["elevenlabs"].get(
            f"{ELEVENLABS_API_BASE}/voices", timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [
            {
                "voice_id": v["voice_id"],
                "name": v["name"],
                "category": v.get("category", ""),
                "labels": v.get("labels", {}),
                "preview_url": v.get("preview_url", ""),
                "active": v["voice_id"] == _elevenlabs_voice_id,
            }
            for v in data.get("voices", [])
        ]
    except Exception as e:
        logger.warning(f"ElevenLabs voices error: {e}")
        return []


# ═══════════════════════════════════════════════════
#  STATUS & CACHE
# ═══════════════════════════════════════════════════

def get_tts_status() -> dict:
    cartesia_key = _get_key("cartesia")
    el_key = _get_key("elevenlabs")
    sapi_available = False
    try:
        import pyttsx3
        sapi_available = True
    except ImportError:
        pass

    # ElevenLabs is primary when enabled + key available (matches _speak_single order)
    if _elevenlabs_enabled and el_key:
        primary = "elevenlabs"
    elif cartesia_key:
        primary = "cartesia"
    elif sapi_available:
        primary = "sapi"
    else:
        primary = "none"

    return {
        "available": bool(cartesia_key) or bool(el_key) or sapi_available,
        "engine": primary,
        "cartesia_available": bool(cartesia_key),
        "cartesia_model": _cartesia_model,
        "cartesia_voice_id": _cartesia_voice_id,
        "elevenlabs_available": bool(el_key),
        "elevenlabs_enabled": _elevenlabs_enabled,
        "elevenlabs_voice_id": _elevenlabs_voice_id,
        "elevenlabs_model": _elevenlabs_model,
        "elevenlabs_has_key": bool(el_key),
        "sapi_available": sapi_available,
        "ready": bool(cartesia_key) or bool(el_key) or sapi_available,
        "cache_dir": str(AUDIO_CACHE_DIR),
    }


def clear_cache():
    count = 0
    for f in AUDIO_CACHE_DIR.glob("tts_*.*"):
        f.unlink()
        count += 1
    logger.info(f"TTS cache cleared ({count} files)")

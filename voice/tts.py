"""Lexa AI — Text-to-Speech v2 (Cartesia Sonic + ElevenLabs + SAPI)

Primary: Cartesia Sonic 2 (HTTP, ~90ms TTFB, cheap)
Fallback: ElevenLabs Turbo v2.5 (HTTP streaming, ~75ms, best quality)
Offline: Windows SAPI via pyttsx3

Audio caching by content hash prevents re-generation.
Text chunking at sentence boundaries for long responses.
"""

import re
import time
import logging
import hashlib
import asyncio
import requests
from pathlib import Path

from voice.config import (
    AUDIO_CACHE_DIR,
    OPENAI_AUDIO_BASE_URL, OPENAI_TTS_MODEL, OPENAI_TTS_VOICE,
    CARTESIA_API_URL, CARTESIA_MODEL, CARTESIA_VOICE_ID, CARTESIA_OUTPUT_FORMAT,
    ELEVENLABS_API_BASE, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL,
    ELEVENLABS_STABILITY, ELEVENLABS_SIMILARITY, ELEVENLABS_STYLE,
    MAX_TTS_CHUNK_CHARS, MAX_TTS_TEXT_CHARS, TTS_PROVIDER_ORDER,
    TTS_CACHE_MAX_AGE_DAYS, TTS_CACHE_MAX_FILES, TTS_CACHE_MAX_MB,
)

logger = logging.getLogger("lexa.tts")

# ═══════════════════════════════════════════════════
#  API KEY MANAGEMENT
# ═══════════════════════════════════════════════════

_keys: dict[str, str | None] = {"openai": None, "cartesia": None, "elevenlabs": None}
_keys_loaded: dict[str, bool] = {"openai": False, "cartesia": False, "elevenlabs": False}

# Persistent HTTP sessions
_sessions: dict[str, requests.Session] = {
    "openai": requests.Session(),
    "cartesia": requests.Session(),
    "elevenlabs": requests.Session(),
}
_sessions["elevenlabs"].headers.update({
    "Content-Type": "application/json",
    "Accept": "audio/mpeg",
})


def _get_key(provider: str) -> str | None:
    # Cache flag wird unabhaengig vom Ergebnis gesetzt, damit ein fehlender Key
    # gemerkt wird und Keyring nicht bei jedem Aufruf erneut (blockierend)
    # abgefragt wird. set_*_key aktualisiert den Cache, falls der Key spaeter
    # gesetzt wird.
    if _keys_loaded[provider]:
        return _keys[provider]
    try:
        import keyring
        key_names = {
            "openai": "openai_api_key",
            "cartesia": "cartesia_api_key",
            "elevenlabs": "elevenlabs_api_key",
        }
        _keys[provider] = keyring.get_password("lexa-ai", key_names[provider])
    except Exception:
        _keys[provider] = None
    _keys_loaded[provider] = True
    if _keys[provider] and provider == "elevenlabs":
        _sessions["elevenlabs"].headers["xi-api-key"] = _keys[provider]
    return _keys[provider]


# ═══════════════════════════════════════════════════
#  MUTABLE CONFIG
# ═══════════════════════════════════════════════════

_cartesia_voice_id = CARTESIA_VOICE_ID
_cartesia_model = CARTESIA_MODEL
_openai_tts_model = OPENAI_TTS_MODEL
_openai_tts_voice = OPENAI_TTS_VOICE
_elevenlabs_voice_id = ELEVENLABS_VOICE_ID
_elevenlabs_model = ELEVENLABS_MODEL
_elevenlabs_stability = ELEVENLABS_STABILITY
_elevenlabs_similarity = ELEVENLABS_SIMILARITY
_elevenlabs_style = ELEVENLABS_STYLE
_elevenlabs_enabled = True
# Effektive TTS-Sprache (aktuell fest "de"; geht in die Cache-Signatur ein,
# damit ein kuenftiger Sprachwechsel den Cache korrekt invalidiert).
_tts_language = "de"
_valid_tts_providers = ("elevenlabs", "cartesia", "openai", "sapi")


def _normalize_provider_order(raw: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(raw, str):
        candidates = raw.split(",")
    else:
        candidates = list(raw)
    order: list[str] = []
    for item in candidates:
        provider = str(item or "").strip().lower()
        if provider in _valid_tts_providers and provider not in order:
            order.append(provider)
    for provider in _valid_tts_providers:
        if provider not in order:
            order.append(provider)
    return order


_tts_provider_order = _normalize_provider_order(TTS_PROVIDER_ORDER)

# Sentence split pattern
_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')


def _sapi_available() -> bool:
    try:
        import pyttsx3  # noqa: F401
        return True
    except ImportError:
        return False


def _provider_available(provider: str) -> bool:
    if provider == "openai":
        return bool(_get_key("openai"))
    if provider == "elevenlabs":
        return bool(_elevenlabs_enabled and _get_key("elevenlabs"))
    if provider == "cartesia":
        return bool(_get_key("cartesia"))
    if provider == "sapi":
        return _sapi_available()
    return False


def _ordered_tts_providers() -> list[str]:
    providers: list[str] = []
    for provider in _tts_provider_order:
        if _provider_available(provider):
            providers.append(provider)
    return providers


def _provider_cache_signature(provider: str) -> str:
    if provider == "openai":
        return "|".join(["openai", _openai_tts_model, _openai_tts_voice, _tts_language])
    if provider == "elevenlabs":
        return "|".join([
            "elevenlabs",
            _elevenlabs_model,
            _elevenlabs_voice_id,
            str(_elevenlabs_stability),
            str(_elevenlabs_similarity),
            str(_elevenlabs_style),
            _tts_language,
        ])
    if provider == "cartesia":
        return "|".join(["cartesia", _cartesia_model, _cartesia_voice_id, _tts_language])
    if provider == "sapi":
        return "|".join(["sapi", "windows-sapi-v1", _tts_language])
    return provider


def _provider_cache_path(text: str, provider: str) -> tuple[str, str]:
    ext = ".wav" if provider == "sapi" else ".mp3"
    cache_input = f"{text}|{_provider_cache_signature(provider)}".encode()
    text_hash = hashlib.sha256(cache_input).hexdigest()[:24]
    return text_hash, str(AUDIO_CACHE_DIR / f"tts_{text_hash}{ext}")


def _cache_files() -> list[Path]:
    try:
        AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return [path for path in AUDIO_CACHE_DIR.glob("tts_*.*") if path.is_file()]
    except OSError as exc:
        logger.warning(f"TTS cache scan failed: {exc}")
        return []


def _cache_entries(files: list[Path] | None = None) -> list[tuple[Path, float, int]]:
    entries: list[tuple[Path, float, int]] = []
    source = files if files is not None else _cache_files()
    for path in source:
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((path, stat.st_mtime, stat.st_size))
    return entries


def _normalize_protected_paths(paths: set[str | Path] | None) -> set[Path]:
    return {Path(path).resolve() for path in (paths or ())}


def _unlink_cache_file(path: Path, protected: set[Path] | None = None) -> bool:
    if protected and path.resolve() in protected:
        return False
    try:
        path.unlink()
        return True
    except OSError as exc:
        logger.warning(f"TTS cache delete failed for {path}: {exc}")
        return False


def _cache_summary_from_entries(entries: list[tuple[Path, float, int]]) -> dict:
    total_bytes = sum(size for _, _, size in entries)
    oldest_mtime = min((mtime for _, mtime, _ in entries), default=None)
    oldest_age_days = 0.0
    if oldest_mtime is not None:
        oldest_age_days = round(max(0.0, time.time() - oldest_mtime) / 86400, 2)
    return {
        "files": len(entries),
        "bytes": total_bytes,
        "mb": round(total_bytes / (1024 * 1024), 2),
        "oldest_age_days": oldest_age_days,
        "max_files": TTS_CACHE_MAX_FILES,
        "max_mb": TTS_CACHE_MAX_MB,
        "max_age_days": TTS_CACHE_MAX_AGE_DAYS,
    }


def _cache_summary() -> dict:
    return _cache_summary_from_entries(_cache_entries())


def _prune_cache(
    *,
    max_files: int = TTS_CACHE_MAX_FILES,
    max_age_days: int = TTS_CACHE_MAX_AGE_DAYS,
    max_mb: int = TTS_CACHE_MAX_MB,
    protected: set[str | Path] | None = None,
) -> dict:
    protected_paths = _normalize_protected_paths(protected)
    entries = _cache_entries()
    removed = 0
    now = time.time()

    if max_age_days > 0:
        max_age_s = max_age_days * 86400
        kept: list[tuple[Path, float, int]] = []
        for entry in entries:
            path, mtime, _ = entry
            if now - mtime > max_age_s and _unlink_cache_file(path, protected_paths):
                removed += 1
            else:
                kept.append(entry)
        entries = kept

    max_bytes = max_mb * 1024 * 1024 if max_mb > 0 else 0
    total_bytes = sum(size for _, _, size in entries)
    remaining = sorted(entries, key=lambda item: item[1])

    while remaining:
        over_file_limit = max_files > 0 and len(remaining) > max_files
        over_size_limit = max_bytes > 0 and total_bytes > max_bytes
        if not over_file_limit and not over_size_limit:
            break

        deleted_index = None
        for index, (path, _, size) in enumerate(remaining):
            if _unlink_cache_file(path, protected_paths):
                removed += 1
                total_bytes -= size
                deleted_index = index
                break

        if deleted_index is None:
            break
        remaining.pop(deleted_index)

    summary = _cache_summary_from_entries(remaining)
    summary["removed_files"] = removed
    return summary


async def _speak_with_provider(provider: str, text: str, target: str) -> str:
    if provider == "openai":
        return await asyncio.to_thread(_speak_openai, text, target)
    if provider == "elevenlabs":
        return await asyncio.to_thread(_speak_elevenlabs, text, target)
    if provider == "cartesia":
        return await asyncio.to_thread(_speak_cartesia, text, target)
    if provider == "sapi":
        if target.endswith(".mp3"):
            # SAPI erzeugt WAV. Wenn der Aufrufer explizit eine .mp3 erwartet,
            # WAV erzeugen und nach .mp3 transkodieren, damit der Rueckgabepfad
            # dem erwarteten output_path entspricht. Ist keine Transkodierung
            # verfuegbar, Fehler werfen statt einen divergenten Pfad
            # zurueckzugeben (der Fallback ueberspringt SAPI dann sauber).
            sapi_path = target[:-len(".mp3")] + ".wav"
            await asyncio.to_thread(_speak_sapi, text, sapi_path)
            return await asyncio.to_thread(_transcode_wav_to_mp3, sapi_path, target)
        return await asyncio.to_thread(_speak_sapi, text, target)
    raise RuntimeError(f"Unknown TTS provider: {provider}")


def _transcode_wav_to_mp3(wav_path: str, mp3_path: str) -> str:
    """Transkodiert eine WAV-Datei nach MP3. Loescht die Quell-WAV bei Erfolg."""
    try:
        from pydub import AudioSegment
    except ImportError:
        try:
            Path(wav_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError("WAV->MP3 transcode requires pydub (not installed)")
    try:
        AudioSegment.from_wav(wav_path).export(mp3_path, format="mp3", bitrate="128k")
    except Exception as e:
        raise RuntimeError(f"WAV->MP3 transcode failed: {e}")
    finally:
        try:
            Path(wav_path).unlink(missing_ok=True)
        except OSError:
            pass
    return mp3_path

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
        "language": _tts_language,
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
    except ImportError:
        logger.info("pydub not installed; using binary MP3 concat fallback")
    except Exception as e:
        logger.warning(f"pydub MP3 concat failed ({e}); using binary concat fallback")

    # Binary concat fallback
    with open(output_path, "wb") as out:
        for cp in chunk_paths:
            with open(cp, "rb") as inp:
                out.write(inp.read())


# ═══════════════════════════════════════════════════
#  OPENAI GPT TTS
# ═══════════════════════════════════════════════════

def _speak_openai(text: str, output_path: str) -> str:
    """Generate speech via OpenAI's current GPT TTS endpoint."""
    api_key = _get_key("openai")
    if not api_key:
        raise RuntimeError("OpenAI API key not configured")

    payload = {
        "model": _openai_tts_model,
        "voice": _openai_tts_voice,
        "input": text[:MAX_TTS_TEXT_CHARS],
        "response_format": "mp3",
    }
    resp = _sessions["openai"].post(
        f"{OPENAI_AUDIO_BASE_URL}/audio/speech",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    if resp.status_code == 200 and resp.content:
        with open(output_path, "wb") as f:
            f.write(resp.content)
        logger.info(f"TTS [OpenAI {_openai_tts_model}/{_openai_tts_voice}]: {output_path}")
        return output_path

    error_msg = resp.text[:200] if hasattr(resp, "text") else "unknown"
    raise RuntimeError(f"OpenAI TTS error {resp.status_code}: {error_msg}")


# ═══════════════════════════════════════════════════
#  MAIN SPEAK FUNCTIONS
# ═══════════════════════════════════════════════════

async def speak_async(text: str, output_path: str = "") -> str:
    """Convert text to speech. Returns absolute path to audio file.
    Fallback chain is provider-locked per response to avoid mixed voices."""
    if not text or not text.strip():
        raise ValueError("Text darf nicht leer sein.")
    text = text.strip()
    if len(text) > MAX_TTS_TEXT_CHARS:
        raise ValueError(f"Text darf maximal {MAX_TTS_TEXT_CHARS} Zeichen lang sein.")

    providers = _ordered_tts_providers()
    if not providers:
        raise RuntimeError("No TTS provider available")

    _prune_cache()
    chunks = _chunk_text(text)
    errors: list[str] = []

    for provider in providers:
        text_hash, cache_path = _provider_cache_path(text, provider)
        target = output_path or cache_path

        if not output_path and Path(cache_path).exists():
            return cache_path

        try:
            if len(chunks) == 1 or provider == "sapi":
                result = await _speak_single(text if provider == "sapi" else chunks[0], target, provider)
            else:
                result = await _speak_multi(chunks, text_hash, target, text, provider)
            if not output_path:
                _prune_cache(protected={result})
            return result
        except Exception as e:
            errors.append(f"{provider}: {e}")
            logger.warning(f"TTS provider {provider} failed for full response: {e}")
            if output_path:
                try:
                    Path(output_path).unlink(missing_ok=True)
                except OSError:
                    pass

    raise RuntimeError("All TTS providers failed: " + "; ".join(errors))


async def _speak_single(text: str, target: str, provider: str | None = None) -> str:
    """Generate one chunk. If provider is set, do not fallback inside the chunk."""
    if provider:
        return await _speak_with_provider(provider, text, target)

    errors: list[str] = []
    for candidate in _ordered_tts_providers():
        try:
            return await _speak_with_provider(candidate, text, target)
        except Exception as e:
            errors.append(f"{candidate}: {e}")
            logger.warning(f"TTS provider {candidate} failed: {e}")
    raise RuntimeError("All TTS providers failed: " + "; ".join(errors))


async def _speak_multi(chunks: list[str], text_hash: str,
                       target: str, full_text: str,
                       provider: str = "elevenlabs") -> str:
    """Multi-chunk generation with one provider for the whole response."""
    if provider == "sapi":
        return await _speak_with_provider(provider, full_text, target)

    logger.info(f"TTS chunking: {len(chunks)} chunks for {len(full_text)} chars via {provider}")
    # Temporaere Chunk-Dateien in ein Unterverzeichnis schreiben, das von
    # _cache_files()/_prune_cache() (nicht-rekursives glob('tts_*.*')) nicht
    # gescannt wird. Verhindert, dass paralleles Pruning oder clear_cache()
    # gerade entstehende Chunks eines anderen Threads loescht.
    chunk_dir = AUDIO_CACHE_DIR / "chunks"
    try:
        chunk_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        chunk_dir = AUDIO_CACHE_DIR
    chunk_paths = []
    try:
        for i, chunk in enumerate(chunks):
            chunk_path = str(chunk_dir / f"tts_{text_hash}_c{i}.mp3")
            await _speak_single(chunk, chunk_path, provider)
            chunk_paths.append(chunk_path)

        _concat_mp3_chunks(chunk_paths, target)

        for cp in chunk_paths:
            try:
                Path(cp).unlink()
            except OSError:
                pass

        logger.info(f"TTS concatenated {len(chunks)} chunks")
        return target
    except Exception:
        for cp in chunk_paths:
            try:
                Path(cp).unlink()
            except OSError:
                pass
        try:
            Path(target).unlink(missing_ok=True)
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
    openai_key = _get_key("openai")
    cartesia_key = _get_key("cartesia")
    el_key = _get_key("elevenlabs")
    sapi_available = _sapi_available()
    provider_order = _ordered_tts_providers()
    cache = _cache_summary()

    # ElevenLabs is primary when enabled + key available (matches _speak_single order)
    primary = provider_order[0] if provider_order else "none"

    return {
        "available": bool(openai_key) or bool(cartesia_key) or bool(el_key) or sapi_available,
        "engine": primary,
        "provider_order": provider_order,
        "configured_provider_order": list(_tts_provider_order),
        "openai_available": bool(openai_key),
        "openai_model": _openai_tts_model,
        "openai_voice": _openai_tts_voice,
        "cartesia_available": bool(cartesia_key),
        "cartesia_model": _cartesia_model,
        "cartesia_voice_id": _cartesia_voice_id,
        "elevenlabs_available": bool(el_key),
        "elevenlabs_enabled": _elevenlabs_enabled,
        "elevenlabs_voice_id": _elevenlabs_voice_id,
        "elevenlabs_model": _elevenlabs_model,
        "elevenlabs_has_key": bool(el_key),
        "sapi_available": sapi_available,
        "ready": bool(openai_key) or bool(cartesia_key) or bool(el_key) or sapi_available,
        "voice_consistency": "provider_locked_per_response",
        "cache_dir": str(AUDIO_CACHE_DIR),
        "cache": cache,
        "cache_files": cache["files"],
        "cache_mb": cache["mb"],
    }


def clear_cache():
    count = 0
    for f in _cache_files():
        if _unlink_cache_file(f):
            count += 1
    logger.info(f"TTS cache cleared ({count} files)")

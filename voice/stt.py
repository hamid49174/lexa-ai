"""Lexa AI — Speech-to-Text v2 (Deepgram Nova-3 + Groq Fallback)

Primary: Deepgram Nova-3 (HTTP batch, ~150ms, best German accuracy)
Fallback: Groq Whisper large-v3-turbo (HTTP batch, ~100ms, free tier)
Offline: Local faster-whisper (CPU)

Circuit breaker with exponential backoff protects against API outages.
"""

import io
import importlib.util
import logging
import os
import re
import threading
import time
import numpy as np
import requests
import soundfile as sf

from voice.config import (
    STT_LANGUAGE as _DEFAULT_LANG,
    STT_ENGINE as _DEFAULT_ENGINE,
    OPENAI_AUDIO_BASE_URL, OPENAI_STT_MODEL,
    DEEPGRAM_HTTP_URL, DEEPGRAM_MODEL,
    GROQ_STT_URL, GROQ_STT_MODEL,
    CB_BASE_RETRY_S, CB_MAX_RETRY_S, CB_MAX_FAILURES,
)
from voice.vad import has_speech

logger = logging.getLogger("lexa.stt")

# ═══════════════════════════════════════════════════
#  MUTABLE STATE
# ═══════════════════════════════════════════════════

STT_LANGUAGE = _DEFAULT_LANG
STT_ENGINE = _DEFAULT_ENGINE

# ═══════════════════════════════════════════════════
#  API KEYS (cached from keyring)
# ═══════════════════════════════════════════════════

_keys: dict[str, str | None] = {"deepgram": None, "groq": None, "openai": None}
_keys_loaded: dict[str, bool] = {"deepgram": False, "groq": False, "openai": False}

# Persistent HTTP sessions (reuse TCP connections)
_sessions: dict[str, requests.Session] = {
    "deepgram": requests.Session(),
    "groq": requests.Session(),
    "openai": requests.Session(),
}


def _get_key(provider: str) -> str | None:
    """Load API key from keyring (cached after first load).

    The cache flag is set regardless of the result, so a missing key is
    remembered and keyring is not re-queried on every transcription. The
    set_*_key helpers refresh the cache when a key is configured later.
    """
    if _keys_loaded[provider]:
        return _keys[provider]
    try:
        import keyring
        key_names = {
            "deepgram": "deepgram_api_key",
            "groq": "groq_api_key",
            "openai": "openai_api_key",
        }
        _keys[provider] = keyring.get_password("lexa-ai", key_names[provider])
    except Exception:
        _keys[provider] = None
    _keys_loaded[provider] = True
    return _keys[provider]


# ═══════════════════════════════════════════════════
#  CIRCUIT BREAKER
# ═══════════════════════════════════════════════════

_fail_counts: dict[str, int] = {"deepgram": 0, "groq": 0, "openai": 0}
_last_fail_times: dict[str, float] = {"deepgram": 0.0, "groq": 0.0, "openai": 0.0}
# Schuetzt das read-modify-write von _fail_counts/_last_fail_times — STT laeuft
# nebenlaeufig (Wakeword-Engine, Conversation-Loop, HTTP-Endpoint via to_thread).
_cb_lock = threading.Lock()


def _circuit_open(provider: str) -> bool:
    with _cb_lock:
        count = _fail_counts.get(provider, 0)
        last = _last_fail_times.get(provider, 0.0)
    # Erst nach CB_MAX_FAILURES echten Fehlern sperren — ein transienter Aussetzer
    # soll den Primaer-Provider nicht sofort fuer Sekunden auf den Fallback zwingen.
    if count < CB_MAX_FAILURES:
        return False
    delay = min(CB_BASE_RETRY_S * (2 ** (count - CB_MAX_FAILURES)), CB_MAX_RETRY_S)
    return (time.time() - last) < delay


def _record_failure(provider: str):
    with _cb_lock:
        _fail_counts[provider] = _fail_counts.get(provider, 0) + 1
        _last_fail_times[provider] = time.time()
        count = _fail_counts[provider]
    if count >= CB_MAX_FAILURES:
        delay = min(CB_BASE_RETRY_S * (2 ** (count - CB_MAX_FAILURES)), CB_MAX_RETRY_S)
        logger.info(f"[CB] {provider} failure #{count} (>= {CB_MAX_FAILURES}), retry after {delay:.0f}s")
    else:
        logger.info(f"[CB] {provider} failure #{count} (Schwelle {CB_MAX_FAILURES})")


def _record_success(provider: str):
    with _cb_lock:
        if _fail_counts.get(provider, 0) > 0:
            _fail_counts[provider] = 0
            _last_fail_times[provider] = 0.0


# ═══════════════════════════════════════════════════
#  AUDIO CONVERSION
# ═══════════════════════════════════════════════════

def _audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return buf.read()


def _mime_for_ext(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
        ".webm": "audio/webm", ".m4a": "audio/mp4", ".flac": "audio/flac",
    }.get(ext, "audio/wav")


def _log_transcription_success(label: str, latency_ms: int, text: str, *, file: bool = False) -> None:
    source = " File" if file else ""
    logger.info("[%s]%s (%sms): textChars=%s", label, source, latency_ms, len(str(text or "")))


# ═══════════════════════════════════════════════════
#  DEEPGRAM NOVA-3 (Primary — best German, ~150ms)
# ═══════════════════════════════════════════════════

def _transcribe_deepgram(audio: np.ndarray, sample_rate: int = 16000,
                         keywords: str = "") -> str | None:
    api_key = _get_key("deepgram")
    if not api_key or _circuit_open("deepgram"):
        return None

    try:
        wav_bytes = _audio_to_wav_bytes(audio, sample_rate)
        params = {
            "model": DEEPGRAM_MODEL,
            "language": STT_LANGUAGE,
            "smart_format": "true",
            "punctuate": "true",
        }
        if keywords:
            params["keyterm"] = keywords

        t0 = time.time()
        resp = _sessions["deepgram"].post(
            DEEPGRAM_HTTP_URL,
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "audio/wav",
            },
            params=params,
            data=wav_bytes,
            timeout=10,
        )
        latency = int((time.time() - t0) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            alts = (data.get("results", {})
                    .get("channels", [{}])[0]
                    .get("alternatives", [{}]))
            text = alts[0].get("transcript", "").strip() if alts else ""
            _log_transcription_success("Deepgram", latency, text)
            _record_success("deepgram")
            return text
        else:
            logger.warning(f"[Deepgram] Error {resp.status_code}: {resp.text[:200]}")
            _record_failure("deepgram")
            return None

    except requests.Timeout:
        logger.warning("[Deepgram] Timeout")
        _record_failure("deepgram")
        return None
    except Exception as e:
        logger.warning(f"[Deepgram] Error: {e}")
        _record_failure("deepgram")
        return None


def _transcribe_deepgram_file(audio_path: str) -> str | None:
    api_key = _get_key("deepgram")
    if not api_key or _circuit_open("deepgram"):
        return None

    try:
        mime = _mime_for_ext(audio_path)
        with open(audio_path, "rb") as f:
            t0 = time.time()
            resp = _sessions["deepgram"].post(
                DEEPGRAM_HTTP_URL,
                headers={
                    "Authorization": f"Token {api_key}",
                    "Content-Type": mime,
                },
                params={
                    "model": DEEPGRAM_MODEL,
                    "language": STT_LANGUAGE,
                    "smart_format": "true",
                    "punctuate": "true",
                },
                data=f.read(),
                timeout=15,
            )
            latency = int((time.time() - t0) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            alts = (data.get("results", {})
                    .get("channels", [{}])[0]
                    .get("alternatives", [{}]))
            text = alts[0].get("transcript", "").strip() if alts else ""
            _log_transcription_success("Deepgram", latency, text, file=True)
            _record_success("deepgram")
            return text
        else:
            logger.warning(f"[Deepgram] File error {resp.status_code}")
            _record_failure("deepgram")
            return None
    except Exception as e:
        logger.warning(f"[Deepgram] File error: {e}")
        _record_failure("deepgram")
        return None


# ═══════════════════════════════════════════════════
#  GROQ WHISPER (Fallback — fastest, free tier)
# ═══════════════════════════════════════════════════

def _transcribe_groq(audio: np.ndarray, sample_rate: int = 16000,
                     prompt: str = "") -> str | None:
    api_key = _get_key("groq")
    if not api_key or _circuit_open("groq"):
        return None

    try:
        wav_bytes = _audio_to_wav_bytes(audio, sample_rate)
        t0 = time.time()
        resp = _sessions["groq"].post(
            GROQ_STT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("audio.wav", wav_bytes, "audio/wav")},
            data={
                "model": GROQ_STT_MODEL,
                "language": STT_LANGUAGE,
                "response_format": "json",
                **({"prompt": prompt} if prompt else {}),
            },
            timeout=10,
        )
        latency = int((time.time() - t0) * 1000)

        if resp.status_code == 200:
            text = resp.json().get("text", "").strip()
            _log_transcription_success("Groq", latency, text)
            _record_success("groq")
            return text
        elif resp.status_code == 429:
            logger.warning("[Groq] Rate limited")
            _record_failure("groq")
            return None
        else:
            logger.warning(f"[Groq] Error {resp.status_code}: {resp.text[:200]}")
            _record_failure("groq")
            return None

    except requests.Timeout:
        logger.warning("[Groq] Timeout")
        _record_failure("groq")
        return None
    except Exception as e:
        logger.warning(f"[Groq] Error: {e}")
        _record_failure("groq")
        return None


def _transcribe_groq_file(audio_path: str) -> str | None:
    api_key = _get_key("groq")
    if not api_key or _circuit_open("groq"):
        return None

    try:
        mime = _mime_for_ext(audio_path)
        with open(audio_path, "rb") as f:
            t0 = time.time()
            resp = _sessions["groq"].post(
                GROQ_STT_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (os.path.basename(audio_path), f, mime)},
                data={
                    "model": GROQ_STT_MODEL,
                    "language": STT_LANGUAGE,
                    "response_format": "json",
                },
                timeout=15,
            )
            latency = int((time.time() - t0) * 1000)

        if resp.status_code == 200:
            text = resp.json().get("text", "").strip()
            _log_transcription_success("Groq", latency, text, file=True)
            _record_success("groq")
            return text
        else:
            logger.warning(f"[Groq] File error {resp.status_code}")
            _record_failure("groq")
            return None
    except Exception as e:
        logger.warning(f"[Groq] File error: {e}")
        _record_failure("groq")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  OPENAI TRANSCRIBE (modern GPT audio fallback / optional primary)
# ══════════════════════════════════════════════════════════════════════════════

def _transcribe_openai(audio: np.ndarray, sample_rate: int = 16000) -> str | None:
    api_key = _get_key("openai")
    if not api_key or _circuit_open("openai"):
        return None

    try:
        wav_bytes = _audio_to_wav_bytes(audio, sample_rate)
        t0 = time.time()
        resp = _sessions["openai"].post(
            f"{OPENAI_AUDIO_BASE_URL}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("audio.wav", wav_bytes, "audio/wav")},
            data={
                "model": OPENAI_STT_MODEL,
                "language": STT_LANGUAGE,
                "response_format": "json",
            },
            timeout=20,
        )
        latency = int((time.time() - t0) * 1000)

        if resp.status_code == 200:
            text = resp.json().get("text", "").strip()
            _log_transcription_success(f"OpenAI STT {OPENAI_STT_MODEL}", latency, text)
            _record_success("openai")
            return text
        logger.warning(f"[OpenAI STT] Error {resp.status_code}: {resp.text[:200]}")
        _record_failure("openai")
        return None
    except requests.Timeout:
        logger.warning("[OpenAI STT] Timeout")
        _record_failure("openai")
        return None
    except Exception as e:
        logger.warning(f"[OpenAI STT] Error: {e}")
        _record_failure("openai")
        return None


def _transcribe_openai_file(audio_path: str) -> str | None:
    api_key = _get_key("openai")
    if not api_key or _circuit_open("openai"):
        return None

    try:
        mime = _mime_for_ext(audio_path)
        with open(audio_path, "rb") as f:
            t0 = time.time()
            resp = _sessions["openai"].post(
                f"{OPENAI_AUDIO_BASE_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (os.path.basename(audio_path), f, mime)},
                data={
                    "model": OPENAI_STT_MODEL,
                    "language": STT_LANGUAGE,
                    "response_format": "json",
                },
                timeout=20,
            )
            latency = int((time.time() - t0) * 1000)

        if resp.status_code == 200:
            text = resp.json().get("text", "").strip()
            _log_transcription_success(f"OpenAI STT {OPENAI_STT_MODEL}", latency, text, file=True)
            _record_success("openai")
            return text
        logger.warning(f"[OpenAI STT] File error {resp.status_code}: {resp.text[:200]}")
        _record_failure("openai")
        return None
    except Exception as e:
        logger.warning(f"[OpenAI STT] File error: {e}")
        _record_failure("openai")
        return None


# ═══════════════════════════════════════════════════
#  LOCAL FALLBACK (faster-whisper, offline)
# ═══════════════════════════════════════════════════

_LOCAL_MODEL_SIZE = "base"
_local_model = None
_local_model_lock = threading.Lock()
_local_loaded_size = None


def _get_local_model():
    global _local_model, _local_loaded_size
    if _local_model is not None and _local_loaded_size == _LOCAL_MODEL_SIZE:
        return _local_model
    with _local_model_lock:
        if _local_model is not None and _local_loaded_size == _LOCAL_MODEL_SIZE:
            return _local_model
        try:
            from faster_whisper import WhisperModel
            _local_model = WhisperModel(_LOCAL_MODEL_SIZE, compute_type="int8")
            _local_loaded_size = _LOCAL_MODEL_SIZE
            logger.info(f"[Local] Model loaded: {_LOCAL_MODEL_SIZE}")
            return _local_model
        except ImportError:
            logger.debug("[Local] faster-whisper not installed")
            return None
        except Exception as e:
            logger.warning(f"[Local] Model load failed: {e}")
            return None


def _transcribe_local(audio: np.ndarray, sample_rate: int = 16000) -> str:
    model = _get_local_model()
    if model is None:
        return ""
    try:
        segments, _ = model.transcribe(
            audio, language=STT_LANGUAGE,
            beam_size=3, best_of=1,
            no_speech_threshold=0.6,
            condition_on_previous_text=False,
        )
        return " ".join(seg.text.strip() for seg in segments)
    except Exception as e:
        logger.warning(f"[Local] Transcribe error: {e}")
        return ""


def _transcribe_local_file(audio_path: str) -> str:
    model = _get_local_model()
    if model is None:
        return ""
    try:
        segments, _ = model.transcribe(
            audio_path, language=STT_LANGUAGE,
            beam_size=3, best_of=1,
            no_speech_threshold=0.6,
        )
        return " ".join(seg.text.strip() for seg in segments)
    except Exception as e:
        logger.warning(f"[Local] File transcribe error: {e}")
        return ""


# ═══════════════════════════════════════════════════
#  PROVIDER CHAIN (selected engine first, then fallbacks)
# ═══════════════════════════════════════════════════

# Default keyterm always boosted on Deepgram (assistant name). Configurable via
# env so deployments can add domain terms (comma-separated).
_DEEPGRAM_KEYTERM = os.environ.get("LEXA_STT_KEYTERM", "Lexa").strip()


def _deepgram_keyterm(prompt: str = "") -> str:
    """Build the Deepgram keyterm: always boost the assistant name, plus any
    distinct terms carried in the prompt."""
    terms = [t.strip() for t in _DEEPGRAM_KEYTERM.split(",") if t.strip()]
    if prompt:
        for t in prompt.split():
            t = t.strip()
            if t and t not in terms:
                terms.append(t)
    return " ".join(terms)


def _get_provider_order() -> list[str]:
    """Build provider order: user-selected STT_ENGINE first, then fallbacks."""
    if STT_ENGINE == "local":
        return []
    fallback_order = ["openai", "deepgram", "groq"]
    selected = STT_ENGINE if STT_ENGINE in fallback_order else "openai"
    return [selected] + [p for p in fallback_order if p != selected]


def _cloud_transcribe(audio: np.ndarray, sample_rate: int = 16000,
                      prompt: str = "") -> str | None:
    providers = _get_provider_order()
    transcribers = {
        "openai": lambda: _transcribe_openai(audio, sample_rate),
        "deepgram": lambda: _transcribe_deepgram(audio, sample_rate,
                                                 keywords=_deepgram_keyterm(prompt)),
        "groq": lambda: _transcribe_groq(audio, sample_rate, prompt=prompt),
    }

    tried_primary = False
    for provider in providers:
        fn = transcribers.get(provider)
        if not fn:
            continue
        result = fn()
        if result is not None:
            if tried_primary:
                logger.info(f"[Fallback] {providers[0]} -> {provider}")
            return result
        tried_primary = True

    return None


def _cloud_transcribe_file(audio_path: str) -> str | None:
    providers = _get_provider_order()
    transcribers = {
        "openai": lambda: _transcribe_openai_file(audio_path),
        "deepgram": lambda: _transcribe_deepgram_file(audio_path),
        "groq": lambda: _transcribe_groq_file(audio_path),
    }

    tried_primary = False
    for provider in providers:
        fn = transcribers.get(provider)
        if not fn:
            continue
        result = fn()
        if result is not None:
            if tried_primary:
                logger.info(f"[Fallback] {providers[0]} -> {provider}")
            return result
        tried_primary = True

    return None


# ═══════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════

def transcribe_file(audio_path: str) -> str:
    """Transcribe audio file. Cloud → Local fallback."""
    if not os.path.exists(audio_path):
        logger.warning(f"[STT] File not found: {audio_path}")
        return ""

    result = _cloud_transcribe_file(audio_path)
    if result is not None:
        return result

    logger.info("[Fallback] Cloud -> Local")
    return _transcribe_local_file(audio_path)


def transcribe_audio_data(audio: np.ndarray, sample_rate: int = 16000) -> str:
    """Transcribe raw audio data. Cloud → Local fallback."""
    if not has_speech(audio):
        return ""

    result = _cloud_transcribe(audio, sample_rate)
    if result is not None:
        return result

    logger.info("[Fallback] Cloud -> Local")
    return _transcribe_local(audio, sample_rate)


def fast_transcribe(audio: np.ndarray, sample_rate: int = 16000) -> str:
    """Fast transcription for wake word detection."""
    if len(audio) == 0:
        return ""
    if not has_speech(audio):
        return ""

    result = _cloud_transcribe(audio, sample_rate, prompt="Lexa")
    if result is not None:
        return result

    # Local fallback with minimal beam for speed
    model = _get_local_model()
    if model is None:
        return ""
    try:
        segments, _ = model.transcribe(
            audio, language=STT_LANGUAGE,
            beam_size=1, best_of=1,
            no_speech_threshold=0.8,
            condition_on_previous_text=False,
        )
        return " ".join(seg.text.strip() for seg in segments)
    except Exception as e:
        logger.warning(f"[Local] Fast transcribe error: {e}")
        return ""


# ═══════════════════════════════════════════════════
#  KEY & ENGINE MANAGEMENT
# ═══════════════════════════════════════════════════

def set_deepgram_key(api_key: str) -> dict:
    if not api_key or not api_key.strip():
        return {"success": False, "error": "API-Key darf nicht leer sein."}
    try:
        import keyring
        api_key = api_key.strip()
        keyring.set_password("lexa-ai", "deepgram_api_key", api_key)
        _keys["deepgram"] = api_key
        _keys_loaded["deepgram"] = True
        logger.info("Deepgram API key saved")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_deepgram_key() -> dict:
    return _delete_provider_key("deepgram_api_key", "deepgram")


def _invalidate_tts_openai_cache() -> None:
    """Den OpenAI-Key-Cache des TTS-Moduls invalidieren.

    OpenAI nutzt EINEN gemeinsamen Keyring-Eintrag fuer STT und TTS; ohne diese
    Invalidierung wuerde der TTS-Pfad bis zum Neustart den alten (Nicht-)Key sehen.
    """
    try:
        from voice import tts as _tts
        _tts._keys_loaded["openai"] = False
        _tts._keys["openai"] = None
    except Exception:
        pass


def _delete_provider_key(keyring_name: str, provider: str, also_tts: bool = False) -> dict:
    """Loescht einen Provider-Key aus dem Keyring und invalidiert IMMER den
    In-Memory-Cache (auch bei fehlendem Key/Fehler) — sonst bliebe ein zuvor
    gesetzter Key bis zum Neustart aktiv, obwohl der Nutzer ihn 'geloescht' hat.
    Ein nicht vorhandener Key zaehlt als Erfolg."""
    result = {"success": True}
    try:
        import keyring
        from keyring.errors import PasswordDeleteError
        try:
            keyring.delete_password("lexa-ai", keyring_name)
        except PasswordDeleteError:
            pass  # bereits geloescht / nie vorhanden -> Erfolg
    except Exception as e:
        result = {"success": False, "error": str(e)}
    finally:
        _keys[provider] = None
        _keys_loaded[provider] = True
        if also_tts:
            _invalidate_tts_openai_cache()
    return result


def set_openai_key(api_key: str) -> dict:
    """OpenAI-Key setzen (gilt fuer OpenAI-STT *und* -TTS — gemeinsamer Keyring-Eintrag)."""
    if not api_key or not api_key.strip():
        return {"success": False, "error": "API-Key darf nicht leer sein."}
    try:
        import keyring
        api_key = api_key.strip()
        keyring.set_password("lexa-ai", "openai_api_key", api_key)
        _keys["openai"] = api_key
        _keys_loaded["openai"] = True
        _invalidate_tts_openai_cache()
        logger.info("OpenAI API key saved")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_openai_key() -> dict:
    return _delete_provider_key("openai_api_key", "openai", also_tts=True)


def set_groq_key(api_key: str) -> dict:
    if not api_key or not api_key.strip():
        return {"success": False, "error": "API-Key darf nicht leer sein."}
    try:
        import keyring
        api_key = api_key.strip()
        keyring.set_password("lexa-ai", "groq_api_key", api_key)
        _keys["groq"] = api_key
        _keys_loaded["groq"] = True
        logger.info("Groq API key saved")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_groq_key() -> dict:
    return _delete_provider_key("groq_api_key", "groq")


def set_engine(engine: str) -> dict:
    global STT_ENGINE
    valid = ("openai", "deepgram", "groq", "local")
    if engine not in valid:
        return {"success": False, "error": f"Unknown engine: {engine}. Use: {', '.join(valid)}"}
    STT_ENGINE = engine
    logger.info(f"STT engine set to: {engine}")
    return {"success": True, "engine": engine}


_VALID_STT_LANG_RE = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")


def set_language(lang: str) -> dict:
    """Set STT language. Validiert den Code (sonst wuerde Muell global ALLE
    Transkription vergiften, bis der Prozess neu startet)."""
    global STT_LANGUAGE
    norm = str(lang or "").strip().lower()
    if norm != "auto" and not _VALID_STT_LANG_RE.match(norm):
        return {"success": False, "error": f"Ungueltiger Sprachcode: {lang!r} (erwartet z.B. 'de', 'en', 'de-de' oder 'auto')."}
    STT_LANGUAGE = norm
    logger.info(f"STT language: {norm}")
    return {"success": True, "language": norm}


def get_model():
    """Oeffentlicher Pre-Warm-Einstieg fuer das lokale Whisper-Modell (main.py-Startup).
    Frueher importierte main.py ein nicht existierendes get_model -> Pre-Warm war tot."""
    return _get_local_model()


def set_model_size(size: str) -> dict:
    global _local_model, _local_loaded_size, _LOCAL_MODEL_SIZE
    allowed = {"tiny", "base", "small", "medium", "large-v3"}
    if size not in allowed:
        return {"success": False, "error": f"Unknown: {size}"}
    _LOCAL_MODEL_SIZE = size
    with _local_model_lock:
        _local_model = None
        _local_loaded_size = None
    return {"success": True, "model": size}


# ═══════════════════════════════════════════════════
#  STATUS
# ═══════════════════════════════════════════════════

STT_MODELS = {
    "openai-gpt-4o-mini-transcribe": {
        "size_mb": 0, "speed": "Schnell", "quality": "Modern GPT audio",
        "desc": "OpenAI Cloud - gpt-4o-mini-transcribe, aktueller GPT-STT Provider",
    },
    "deepgram-nova-3": {
        "size_mb": 0, "speed": "Ultraschnell (~150ms)", "quality": "Exzellent (Deutsch #1)",
        "desc": "Deepgram Cloud — Nova-3, beste deutsche Erkennung",
    },
    "groq-whisper-large-v3-turbo": {
        "size_mb": 0, "speed": "Ultraschnell (~100ms)", "quality": "Exzellent",
        "desc": "Groq Cloud — Whisper large-v3-turbo, schnellstes STT (gratis)",
    },
    "tiny": {"size_mb": 75, "speed": "Sehr schnell", "quality": "Niedrig",
             "desc": "Minimal, fuer schnelle Befehle (lokal)"},
    "base": {"size_mb": 150, "speed": "Schnell", "quality": "Mittel",
             "desc": "Standard lokal — gute Balance"},
    "small": {"size_mb": 500, "speed": "Mittel", "quality": "Gut",
              "desc": "Bessere Erkennung, mehr RAM (lokal)"},
    "medium": {"size_mb": 1500, "speed": "Langsam", "quality": "Sehr gut",
               "desc": "Hochpraezise, braucht viel RAM (lokal)"},
    "large-v3": {"size_mb": 3000, "speed": "Sehr langsam", "quality": "Exzellent",
                 "desc": "Beste lokale Qualitaet, GPU empfohlen"},
}


def get_stt_status() -> dict:
    dg_key = _get_key("deepgram")
    groq_key = _get_key("groq")
    openai_key = _get_key("openai")

    local_available = importlib.util.find_spec("faster_whisper") is not None

    return {
        "ready": bool(openai_key) or bool(dg_key) or bool(groq_key) or local_available,
        "engine": STT_ENGINE,
        "openai_available": bool(openai_key),
        "openai_model": OPENAI_STT_MODEL,
        "deepgram_available": bool(dg_key),
        "deepgram_model": DEEPGRAM_MODEL,
        "groq_available": bool(groq_key),
        "groq_model": GROQ_STT_MODEL,
        "local_available": local_available,
        "local_model_size": _LOCAL_MODEL_SIZE,
        "language": STT_LANGUAGE,
        "vad": "relative_energy",
        "available_models": STT_MODELS,
    }


def get_available_models() -> list[dict]:
    models = []
    openai_key = _get_key("openai")
    models.append({
        "name": "openai-gpt-4o-mini-transcribe", "active": STT_ENGINE == "openai",
        "available": bool(openai_key), **STT_MODELS["openai-gpt-4o-mini-transcribe"],
    })
    dg_key = _get_key("deepgram")
    models.append({
        "name": "deepgram-nova-3", "active": STT_ENGINE == "deepgram",
        "available": bool(dg_key), **STT_MODELS["deepgram-nova-3"],
    })
    groq_key = _get_key("groq")
    models.append({
        "name": "groq-whisper-large-v3-turbo", "active": STT_ENGINE == "groq",
        "available": bool(groq_key), **STT_MODELS["groq-whisper-large-v3-turbo"],
    })
    for size in ("tiny", "base", "small", "medium", "large-v3"):
        available = importlib.util.find_spec("faster_whisper") is not None
        models.append({
            "name": size, "active": STT_ENGINE == "local" and _LOCAL_MODEL_SIZE == size,
            "available": available, **STT_MODELS[size],
        })
    return models

"""Lexa AI — Voice Configuration v2
Single source of truth for all voice-related constants, URLs, and defaults.
"""

import os
from pathlib import Path

# ══════════════════════════════════════════════════
#  PATHS
# ══════════════════════════════════════════════════

VOICE_DIR = Path(__file__).resolve().parent
_DATA_DIR = os.environ.get("LEXA_DATA_DIR", str(VOICE_DIR.parent))
AUDIO_CACHE_DIR = (Path(_DATA_DIR) / "audio_cache").resolve()
AUDIO_CACHE_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════
#  AUDIO
# ══════════════════════════════════════════════════

SAMPLE_RATE = 16000              # 16kHz — standard for all STT models
VAD_CHUNK_SAMPLES = 480          # 30ms at 16kHz (WebRTC-compatible)
RECORD_CHUNK_MS = 30             # Milliseconds per chunk

# ══════════════════════════════════════════════════
#  STT PROVIDERS
# ══════════════════════════════════════════════════

STT_LANGUAGE = "de"
STT_ENGINE = "openai"            # "openai" (modern) | "deepgram" | "groq" | "local"

# OpenAI current audio stack (optional, used when an OpenAI key is available)
OPENAI_AUDIO_BASE_URL = "https://api.openai.com/v1"
OPENAI_STT_MODEL = "gpt-4o-mini-transcribe"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_TTS_VOICE = os.environ.get("LEXA_OPENAI_TTS_VOICE", "nova").strip() or "nova"
OPENAI_REALTIME_MODEL = "gpt-realtime-2"

# Deepgram Nova-3 (WebSocket streaming, ~150ms, best German)
DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
DEEPGRAM_HTTP_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_MODEL = "nova-3"
DEEPGRAM_ENDPOINTING_MS = 800   # Silence duration to detect end of utterance

# Groq Whisper (HTTP batch fallback, ~100ms, free tier)
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_STT_MODEL = "whisper-large-v3-turbo"

# ══════════════════════════════════════════════════
#  TTS PROVIDERS
# ══════════════════════════════════════════════════

TTS_ENGINE = "elevenlabs"        # Legacy primary label; order below is authoritative
TTS_PROVIDER_ORDER = os.environ.get(
    "LEXA_TTS_PROVIDER_ORDER",
    "elevenlabs,cartesia,openai,sapi",
)

# Cartesia Sonic Turbo (WebSocket streaming, 40ms TTFB)
CARTESIA_API_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_WS_URL = "wss://api.cartesia.ai/tts/websocket"
CARTESIA_MODEL = "sonic-2"
CARTESIA_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"  # Valentino (German)
CARTESIA_OUTPUT_FORMAT = {
    "container": "mp3",
    "bit_rate": 128000,
    "sample_rate": 44100,
}

# ElevenLabs Turbo v2.5 (HTTP streaming fallback, ~75ms)
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
ELEVENLABS_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Sarah (premade)
ELEVENLABS_MODEL = "eleven_turbo_v2_5"
ELEVENLABS_STABILITY = 0.5
ELEVENLABS_SIMILARITY = 0.75
ELEVENLABS_STYLE = 0.0

# ══════════════════════════════════════════════════
#  VAD (Voice Activity Detection)
# ══════════════════════════════════════════════════

PRE_SPEECH_CHUNKS = 10           # 10 × 30ms = 300ms ring buffer
SILENCE_MS_BASE = 800            # 800ms silence = end of utterance
SILENCE_MS_SHORT = 500           # Shorter if utterance ends with .!?
MIN_SPEECH_MS = 200              # Ignore bursts shorter than 200ms

# ══════════════════════════════════════════════════
#  WAKE WORD
# ══════════════════════════════════════════════════

WAKE_PHRASES = [
    "lexa", "alexa", "lex a", "leksa", "lexi", "lexer",
    "läxa", "lexar", "lex", "leka", "lecka", "lechsa",
    "hey lexa", "hei lexa", "ok lexa", "okay lexa",
]

EXIT_PHRASES = {
    "danke", "tschüss", "tschüs", "das wars", "das war's",
    "stop", "stopp", "ende", "halt", "genug", "aufhören",
    "bis später", "ciao", "bye", "fertig", "schluss",
}

WAKE_COOLDOWN_S = 2.0            # Between wake word detections
WAKE_WINDOW_S = 0.32             # 4 x 80ms frames, aligned with openWakeWord streaming
WAKE_STEP_S = 0.32               # Kept for diagnostics/config parity
WAKE_ENGINE = os.environ.get("LEXA_WAKE_ENGINE", "openwakeword").strip().lower() or "openwakeword"
WAKE_OPENWAKEWORD_MODELS = os.environ.get("LEXA_OPENWAKEWORD_MODELS", "alexa").strip() or "alexa"
WAKE_OPENWAKEWORD_THRESHOLD = float(os.environ.get("LEXA_OPENWAKEWORD_THRESHOLD", "0.55"))
WAKE_OPENWAKEWORD_PATIENCE = int(os.environ.get("LEXA_OPENWAKEWORD_PATIENCE", "2"))
WAKE_OPENWAKEWORD_VAD_THRESHOLD = float(os.environ.get("LEXA_OPENWAKEWORD_VAD_THRESHOLD", "0.05"))
WAKE_OPENWAKEWORD_AUTO_DOWNLOAD = os.environ.get("LEXA_OPENWAKEWORD_AUTO_DOWNLOAD", "1").strip().lower() in {"1", "true", "yes", "on"}
WAKE_PORCUPINE_ACCESS_KEY = os.environ.get("LEXA_PORCUPINE_ACCESS_KEY") or os.environ.get("PICOVOICE_ACCESS_KEY", "")
WAKE_PORCUPINE_KEYWORDS = os.environ.get("LEXA_PORCUPINE_KEYWORDS", "")
WAKE_PORCUPINE_KEYWORD_PATHS = os.environ.get("LEXA_PORCUPINE_KEYWORD_PATHS", "")
WAKE_PORCUPINE_SENSITIVITY = float(os.environ.get("LEXA_PORCUPINE_SENSITIVITY", "0.55"))
WAKE_LEGACY_TRANSCRIPT_ENABLED = os.environ.get("LEXA_WAKE_LEGACY_TRANSCRIPT_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
WAKE_FALLBACK_STT_MIN_INTERVAL_S = float(os.environ.get("LEXA_WAKE_FALLBACK_STT_MIN_INTERVAL_S", "0.75"))
WAKE_FALLBACK_STT_MAX_INTERVAL_S = float(os.environ.get("LEXA_WAKE_FALLBACK_STT_MAX_INTERVAL_S", "1.5"))
WAKE_FALLBACK_STT_BACKOFF_STEP_S = float(os.environ.get("LEXA_WAKE_FALLBACK_STT_BACKOFF_STEP_S", "0.25"))

# ══════════════════════════════════════════════════
#  BARGE-IN (user interrupts AI while speaking)
# ══════════════════════════════════════════════════

BARGEIN_THRESHOLD = 0.04         # High threshold to avoid TTS echo
BARGEIN_MIN_CHUNKS = 5           # ~150ms sustained loud speech
BARGEIN_WARMUP_S = 0.4           # Ignore audio for 400ms after playback starts

# ══════════════════════════════════════════════════
#  TIMEOUTS
# ══════════════════════════════════════════════════

LISTEN_TIMEOUT_S = 15            # Wait 15s for speech to start
MAX_UTTERANCE_S = 25             # Max single utterance length

# ══════════════════════════════════════════════════
#  CIRCUIT BREAKER
# ══════════════════════════════════════════════════

CB_BASE_RETRY_S = 10.0           # Base retry delay
CB_MAX_RETRY_S = 300.0           # Max retry delay (5 min)
CB_MAX_FAILURES = 3              # Failures before circuit opens

# ══════════════════════════════════════════════════
#  TEXT PROCESSING
# ══════════════════════════════════════════════════

MAX_TTS_CHUNK_CHARS = 500        # Cartesia max per request
MAX_TTS_TEXT_CHARS = 2000        # Safety cap

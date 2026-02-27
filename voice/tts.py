"""Lexa AI — Text-to-Speech via Piper (lokal, kein API)"""

import subprocess
import logging
import wave
import io
from pathlib import Path

logger = logging.getLogger("lexa.tts")

VOICE_DIR = Path(__file__).resolve().parent
PIPER_EXE = VOICE_DIR / "piper" / "piper" / "piper.exe"
MODEL_PATH = VOICE_DIR / "piper" / "de_thorsten_medium.onnx"
AUDIO_DIR = VOICE_DIR / "audio_cache"
AUDIO_DIR.mkdir(exist_ok=True)


def speak(text: str, output_path: str = "") -> str:
    """Convert text to speech using Piper TTS. Returns path to WAV file."""
    if not PIPER_EXE.exists():
        raise FileNotFoundError(f"Piper not found at {PIPER_EXE}")
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Voice model not found at {MODEL_PATH}")

    if not output_path:
        import hashlib
        text_hash = hashlib.md5(text.encode()).hexdigest()[:12]
        output_path = str(AUDIO_DIR / f"tts_{text_hash}.wav")

    # Check cache
    if Path(output_path).exists():
        return output_path

    try:
        result = subprocess.run(
            [
                str(PIPER_EXE),
                "--model", str(MODEL_PATH),
                "--output_file", output_path,
            ],
            input=text,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error(f"Piper error: {result.stderr}")
            raise RuntimeError(f"Piper TTS failed: {result.stderr}")

        logger.info(f"TTS generated: {output_path}")
        return output_path

    except subprocess.TimeoutExpired:
        raise RuntimeError("Piper TTS timeout")


def get_audio_duration(wav_path: str) -> float:
    """Get duration of a WAV file in seconds."""
    with wave.open(wav_path, "r") as w:
        frames = w.getnframes()
        rate = w.getframerate()
        return frames / rate


def clear_cache():
    """Clear TTS audio cache."""
    for f in AUDIO_DIR.glob("tts_*.wav"):
        f.unlink()
    logger.info("TTS cache cleared")

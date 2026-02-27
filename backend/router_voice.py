"""Lexa AI — Voice Router
API Endpoints für STT und TTS
"""

import io
import tempfile
import logging
from pathlib import Path
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse

from backend.security import check_rate_limit, audit_log

logger = logging.getLogger("lexa.voice")
router = APIRouter(prefix="/voice", tags=["voice"])

TEMP_DIR = Path(tempfile.gettempdir()) / "lexa_voice"
TEMP_DIR.mkdir(exist_ok=True)


@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """Convert uploaded audio to text via faster-whisper."""
    if not check_rate_limit():
        return {"error": "Rate limit erreicht."}

    # Save uploaded audio
    audio_path = TEMP_DIR / f"stt_{audio.filename}"
    content = await audio.read()
    with open(audio_path, "wb") as f:
        f.write(content)

    try:
        from voice.stt import transcribe_file
        text = transcribe_file(str(audio_path))
        audit_log("stt", "transcribed", f"text={text[:80]}")
        return {"text": text, "success": True}
    except Exception as e:
        logger.error(f"STT error: {e}")
        return {"text": "", "success": False, "error": str(e)}
    finally:
        audio_path.unlink(missing_ok=True)


@router.post("/tts")
async def text_to_speech(data: dict):
    """Convert text to speech via Piper TTS. Returns WAV file."""
    text = data.get("text", "")
    if not text:
        return {"error": "Kein Text angegeben."}

    if not check_rate_limit():
        return {"error": "Rate limit erreicht."}

    try:
        from voice.tts import speak
        wav_path = speak(text)
        audit_log("tts", "generated", f"text={text[:50]}")
        return FileResponse(
            wav_path,
            media_type="audio/wav",
            filename="lexa_response.wav",
        )
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return {"error": str(e)}


@router.get("/tts/status")
async def tts_status():
    """Check if TTS is available."""
    from voice.tts import PIPER_EXE, MODEL_PATH
    return {
        "piper_installed": PIPER_EXE.exists(),
        "model_installed": MODEL_PATH.exists(),
        "ready": PIPER_EXE.exists() and MODEL_PATH.exists(),
    }


@router.get("/stt/status")
async def stt_status():
    """Check if STT is available."""
    try:
        import faster_whisper
        return {"ready": True, "engine": "faster-whisper"}
    except ImportError:
        return {"ready": False, "error": "faster-whisper nicht installiert"}

"""Lexa AI — Speech-to-Text via faster-whisper (lokal, kein API)"""

import logging
import threading
import queue
import numpy as np

logger = logging.getLogger("lexa.stt")

# Lazy-load model to avoid slow startup
_model = None
_model_lock = threading.Lock()


def get_model():
    """Load whisper model (lazy, thread-safe)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from faster_whisper import WhisperModel
                logger.info("Loading Whisper model (base)...")
                _model = WhisperModel(
                    "base",
                    device="cpu",
                    compute_type="int8",
                )
                logger.info("Whisper model loaded.")
    return _model


def transcribe_file(audio_path: str) -> str:
    """Transcribe an audio file to text."""
    model = get_model()
    segments, info = model.transcribe(
        audio_path,
        language="de",
        beam_size=5,
    )
    text = " ".join(seg.text.strip() for seg in segments)
    logger.info(f"Transcribed ({info.duration:.1f}s): {text[:80]}...")
    return text


def transcribe_audio_data(audio_data: np.ndarray, sample_rate: int = 16000) -> str:
    """Transcribe raw audio data (numpy array) to text."""
    model = get_model()
    segments, info = model.transcribe(
        audio_data,
        language="de",
        beam_size=5,
    )
    text = " ".join(seg.text.strip() for seg in segments)
    logger.info(f"Transcribed ({info.duration:.1f}s): {text[:80]}...")
    return text


class LiveRecorder:
    """Record audio from microphone for STT."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        self._audio_queue = queue.Queue()
        self._frames = []

    def start(self):
        """Start recording from microphone."""
        import sounddevice as sd

        self.is_recording = True
        self._frames = []

        def callback(indata, frames, time_info, status):
            if self.is_recording:
                self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=callback,
        )
        self._stream.start()
        logger.info("Recording started")

    def stop(self) -> np.ndarray:
        """Stop recording and return audio data."""
        self.is_recording = False
        self._stream.stop()
        self._stream.close()
        logger.info(f"Recording stopped ({len(self._frames)} frames)")

        if not self._frames:
            return np.array([], dtype=np.float32)

        audio = np.concatenate(self._frames, axis=0).flatten()
        return audio

    def stop_and_transcribe(self) -> str:
        """Stop recording and transcribe."""
        audio = self.stop()
        if len(audio) == 0:
            return ""
        return transcribe_audio_data(audio, self.sample_rate)

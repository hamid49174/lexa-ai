"""Lexa AI — Audio Playback v2
Windows MCI-based audio player with barge-in detection.
Separated from conversation logic for clean architecture.
"""

import ctypes
import logging
import time
import numpy as np
from typing import Optional, Callable

from voice.config import (
    SAMPLE_RATE, VAD_CHUNK_SAMPLES, RECORD_CHUNK_MS,
    BARGEIN_THRESHOLD, BARGEIN_MIN_CHUNKS, BARGEIN_WARMUP_S,
)

logger = logging.getLogger("lexa.playback")

# ══════════════════════════════════════════════════
#  WINDOWS MCI (low-level, no dependencies)
# ══════════════════════════════════════════════════

_winmm = None
try:
    _winmm = ctypes.windll.winmm
except Exception:
    pass


def _mci(cmd: str):
    if _winmm:
        _winmm.mciSendStringW(cmd, None, 0, None)


def _mci_playing() -> bool:
    if not _winmm:
        return False
    buf = ctypes.create_unicode_buffer(256)
    _winmm.mciSendStringW("status lexa_conv mode", buf, 256, None)
    return buf.value == "playing"


class AudioPlayer:
    """MCI-based audio player with barge-in monitoring."""

    def __init__(self, on_volume: Optional[Callable[[float], None]] = None):
        self.on_volume = on_volume
        self._playing = False

    def play_file(self, path: str) -> None:
        """Play audio file via MCI (blocking until done or stopped)."""
        _mci("close lexa_conv")
        safe_path = path.replace('"', "")
        _mci(f'open "{safe_path}" type mpegvideo alias lexa_conv')
        _mci("play lexa_conv")
        self._playing = True

    def stop(self) -> None:
        """Stop playback immediately."""
        _mci("stop lexa_conv")
        _mci("close lexa_conv")
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return _mci_playing()

    def play_files_with_bargein(self, audio_paths: list[str], sd,
                                is_active: Callable[[], bool],
                                noise_floor: float = 0.0) -> Optional[np.ndarray]:
        """Play audio files sequentially, monitoring mic for user interruption.

        Returns captured barge-in audio (numpy) or None if played to completion.

        Echo avoidance:
          - 400ms warmup delay after each file starts
          - Higher energy threshold during playback
          - Requires 5 consecutive loud chunks (~150ms sustained speech)
        """
        sr = SAMPLE_RATE
        chunk_samples = VAD_CHUNK_SAMPLES

        for path in audio_paths:
            if not is_active():
                self.stop()
                return None

            self.play_file(path)

            adaptive_threshold = max(BARGEIN_THRESHOLD, noise_floor * 4.0)
            warmup_chunks = int(BARGEIN_WARMUP_S / (RECORD_CHUNK_MS / 1000))
            warmup_count = 0
            speech_count = 0
            bargein_audio: list[np.ndarray] = []

            while is_active() and self.is_playing:
                try:
                    chunk = sd.rec(chunk_samples, samplerate=sr, channels=1, dtype="float32")
                    sd.wait(ignore_errors=True)
                except Exception:
                    self.stop()
                    return None

                if not is_active():
                    self.stop()
                    return None

                flat = chunk.flatten()
                rms = np.sqrt(np.mean(flat ** 2))
                warmup_count += 1

                if self.on_volume:
                    self.on_volume(rms)

                # Skip barge-in check during warmup (echo avoidance)
                if warmup_count < warmup_chunks:
                    continue

                if rms >= adaptive_threshold:
                    speech_count += 1
                    bargein_audio.append(flat)

                    if speech_count >= BARGEIN_MIN_CHUNKS:
                        self.stop()
                        logger.info(f"[Bargein] User interrupted after {warmup_count} chunks")

                        # Record the rest of the user's utterance
                        rest = self._record_rest(sd, is_active,
                                                 adaptive_threshold=adaptive_threshold)
                        if rest is not None:
                            bargein_audio.append(rest)

                        return np.concatenate(bargein_audio) if bargein_audio else None
                else:
                    speech_count = 0
                    bargein_audio.clear()

            self.stop()

        return None  # Played to completion

    def _record_rest(self, sd, is_active: Callable[[], bool],
                     timeout_s: float = 5, max_s: float = 15,
                     adaptive_threshold: float = 0.0) -> Optional[np.ndarray]:
        """Record remaining speech after barge-in detection."""
        sr = SAMPLE_RATE
        chunk_samples = VAD_CHUNK_SAMPLES
        chunks = []
        silence = 0
        silence_needed = int(800 / RECORD_CHUNK_MS)  # 800ms silence
        max_chunks = int(max_s * sr / chunk_samples)

        for _ in range(max_chunks):
            if not is_active():
                break
            try:
                chunk = sd.rec(chunk_samples, samplerate=sr, channels=1, dtype="float32")
                sd.wait()
            except Exception:
                break

            flat = chunk.flatten()
            chunks.append(flat)
            rms = np.sqrt(np.mean(flat ** 2))

            silence_threshold = adaptive_threshold * 0.5 if adaptive_threshold > 0 else BARGEIN_THRESHOLD * 0.5
            if rms < silence_threshold:
                silence += 1
                if silence >= silence_needed:
                    break
            else:
                silence = 0

        return np.concatenate(chunks) if chunks else None

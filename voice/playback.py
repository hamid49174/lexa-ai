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


def _mci_mode() -> str:
    """Return the raw MCI mode string (e.g. 'playing', 'stopped', '')."""
    if not _winmm:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    _winmm.mciSendStringW("status lexa_conv mode", buf, 256, None)
    return buf.value


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

    def _wait_until_playing(self, is_active: Callable[[], bool],
                            timeout_s: float = 1.0) -> bool:
        """Poll MCI after a 'play' command until it confirms 'playing' status.

        MCI does not guarantee the mode flips to 'playing' the instant the
        synchronous 'play' command returns; right after the start (and at file
        transitions) it can briefly report a different mode. Without this wait
        the monitoring loop would see is_playing == False immediately and skip
        barge-in monitoring for the file. Returns True once 'playing' is
        confirmed, False on timeout or if playback already finished/aborted.
        """
        if not _winmm:
            return False
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not is_active():
                return False
            mode = _mci_mode()
            if mode == "playing":
                return True
            # Very short clips can already be done before we observe 'playing'.
            if mode == "stopped":
                return False
            time.sleep(0.01)
        return _mci_mode() == "playing"

    def play_files_with_bargein(self, audio_paths: list[str], sd,
                                is_active: Callable[[], bool],
                                noise_floor: float = 0.0) -> Optional[np.ndarray]:
        """Play audio files sequentially, monitoring mic for user interruption.

        Returns captured barge-in audio (numpy) or None if played to completion.

        Echo avoidance:
          - 400ms warmup delay after each file starts
          - Higher energy threshold during playback
          - Requires 5 consecutive loud chunks (~150ms sustained speech)

        A single persistent sd.InputStream is opened for the whole call (same
        pattern as _record_utterance) so the mic is not re-opened per 30ms
        chunk — this avoids per-iteration device-setup latency and the audio
        gaps that would otherwise swallow the first syllables of a barge-in.
        """
        sr = SAMPLE_RATE
        chunk_samples = VAD_CHUNK_SAMPLES

        adaptive_threshold = max(BARGEIN_THRESHOLD, noise_floor * 4.0)
        warmup_chunks = int(BARGEIN_WARMUP_S / (RECORD_CHUNK_MS / 1000))

        try:
            with sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                                blocksize=chunk_samples) as stream:
                for path in audio_paths:
                    if not is_active():
                        self.stop()
                        return None

                    self.play_file(path)

                    # Wait for MCI to confirm playback actually started before
                    # monitoring — otherwise is_playing may read False right away
                    # and we would skip barge-in detection for this file.
                    if not self._wait_until_playing(is_active):
                        # Either aborted, MCI unavailable, or a very short clip
                        # already finished. Move on to the next file.
                        self.stop()
                        continue

                    warmup_count = 0
                    speech_count = 0
                    bargein_audio: list[np.ndarray] = []

                    while is_active() and self.is_playing:
                        try:
                            chunk, _overflowed = stream.read(chunk_samples)
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

                                # Record the rest of the user's utterance on the
                                # same already-open stream (no gap, no re-setup).
                                rest = self._record_rest(stream, is_active,
                                                         adaptive_threshold=adaptive_threshold)
                                if rest is not None:
                                    bargein_audio.append(rest)

                                return np.concatenate(bargein_audio) if bargein_audio else None
                        else:
                            speech_count = 0
                            bargein_audio.clear()

                    self.stop()
        except Exception:
            self.stop()
            return None

        return None  # Played to completion

    def _record_rest(self, stream, is_active: Callable[[], bool],
                     timeout_s: float = 5, max_s: float = 15,
                     adaptive_threshold: float = 0.0) -> Optional[np.ndarray]:
        """Record remaining speech after barge-in detection.

        Reads from an already-open sd.InputStream (handed in by the caller) to
        avoid re-opening the mic per chunk. Stops on 800ms of trailing silence,
        on the absolute cap max_s, or — if no above-threshold speech is heard at
        all within timeout_s of starting — on the timeout (handles the case
        where the barge-in was a transient noise and no real utterance follows).
        """
        sr = SAMPLE_RATE
        chunk_samples = VAD_CHUNK_SAMPLES
        chunks = []
        silence = 0
        silence_needed = int(800 / RECORD_CHUNK_MS)  # 800ms silence
        max_chunks = int(max_s * sr / chunk_samples)
        timeout_chunks = int(timeout_s * sr / chunk_samples)

        silence_threshold = (adaptive_threshold * 0.5 if adaptive_threshold > 0
                             else BARGEIN_THRESHOLD * 0.5)
        speech_seen = False

        for i in range(max_chunks):
            if not is_active():
                break
            try:
                chunk, _overflowed = stream.read(chunk_samples)
            except Exception:
                break

            flat = chunk.flatten()
            chunks.append(flat)
            rms = np.sqrt(np.mean(flat ** 2))

            if rms < silence_threshold:
                silence += 1
                # No real follow-up speech within timeout_s → give up early
                # instead of recording up to max_s of (near-)silence.
                if not speech_seen and i + 1 >= timeout_chunks:
                    break
                if silence >= silence_needed:
                    break
            else:
                speech_seen = True
                silence = 0

        return np.concatenate(chunks) if chunks else None

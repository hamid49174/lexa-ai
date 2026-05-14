"""Lexa AI — Voice Activity Detection v2
Relative energy-based VAD — works with ANY microphone gain level.
No absolute thresholds. Compares chunk energy to noise floor + running peak.
Cloud STT makes the final decision — this only gates when to start/stop recording.
"""

import logging
import numpy as np

from voice.config import (
    SAMPLE_RATE, VAD_CHUNK_SAMPLES, SILENCE_MS_BASE, RECORD_CHUNK_MS,
)

logger = logging.getLogger("lexa.vad")


def is_speech(audio_chunk: np.ndarray, peak_rms: float = 0.0,
              noise_floor: float = 0.0) -> bool:
    """Relative energy speech detection — mic-independent.

    Compares chunk RMS to the recording's peak RMS and noise floor.
    Uses dynamic range analysis instead of absolute thresholds.

    Args:
        audio_chunk: float32 audio, VAD_CHUNK_SAMPLES at 16kHz
        peak_rms: highest RMS seen so far in this recording
        noise_floor: calibrated ambient noise RMS
    """
    rms = np.sqrt(np.mean(audio_chunk ** 2))

    # If we have a peak reference, use relative detection
    if peak_rms > 0 and peak_rms > noise_floor * 1.5:
        dynamic_range = peak_rms - noise_floor
        threshold = noise_floor + dynamic_range * 0.25
        return rms > threshold

    # No reference yet — just check if louder than noise
    if noise_floor > 0:
        return rms > noise_floor * 2.0

    # Last resort
    return rms > 0.0005


def has_speech(audio: np.ndarray, threshold: float = 0.001,
               min_ratio: float = 0.005) -> bool:
    """Ultra-permissive speech check — only filters dead silence.
    Cloud STT is far better at rejecting noise than local checks.
    Let the API decide if there's real speech."""
    if len(audio) == 0:
        return False
    above = np.sum(np.abs(audio) > threshold) / len(audio)
    result = above >= min_ratio
    if not result:
        logger.debug(f"[VAD] Silent audio filtered (ratio={above:.4f})")
    return result


def calibrate_noise_floor(sd, duration_s: float = 1.0) -> tuple[float, float]:
    """Record ambient noise and return (noise_floor, sensitivity_gate).

    Args:
        sd: sounddevice module
        duration_s: calibration duration

    Returns:
        (noise_floor_rms, wake_sensitivity)
    """
    sr = SAMPLE_RATE
    chunk_samples = VAD_CHUNK_SAMPLES
    cal_chunks = int(sr * duration_s) // chunk_samples

    rms_values = []
    for _ in range(cal_chunks):
        try:
            chunk = sd.rec(chunk_samples, samplerate=sr, channels=1, dtype="float32")
            sd.wait()
            rms = np.sqrt(np.mean(chunk.flatten() ** 2))
            rms_values.append(rms)
        except Exception:
            break

    if rms_values:
        sorted_rms = sorted(rms_values)
        median_rms = sorted_rms[len(sorted_rms) // 2]
        # Wake word energy gate = 1.5x noise (just skips dead silence)
        sensitivity = max(median_rms * 1.5, 0.0003)
        logger.info(f"[VAD] Calibrated: noise={median_rms:.6f}, gate={sensitivity:.5f}")
        return median_rms, sensitivity

    logger.warning("[VAD] Calibration failed, using defaults")
    return 0.0001, 0.0003


def reset():
    """Reset VAD state between conversations. (Stateless — no-op)"""
    pass

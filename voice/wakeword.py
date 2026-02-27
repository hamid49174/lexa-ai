"""Lexa AI — Wake Word Detection
Simple energy-based VAD + keyword matching as lightweight alternative.
Uses a continuous listening loop that triggers on 'hey lexa' detection.
"""

import logging
import threading
import time
import numpy as np

logger = logging.getLogger("lexa.wakeword")


class WakeWordDetector:
    """Lightweight wake word detector using STT."""

    def __init__(self, wake_phrase: str = "hey lexa", callback=None):
        self.wake_phrase = wake_phrase.lower()
        self.callback = callback
        self.is_listening = False
        self._thread = None
        self.sensitivity = 0.02  # Energy threshold for VAD

    def start(self):
        """Start listening for wake word in background."""
        if self.is_listening:
            return

        self.is_listening = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info(f"Wake word detector started (phrase: '{self.wake_phrase}')")

    def stop(self):
        """Stop listening."""
        self.is_listening = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Wake word detector stopped")

    def _listen_loop(self):
        """Continuous listening loop."""
        import sounddevice as sd

        sample_rate = 16000
        chunk_duration = 2.0  # seconds per chunk
        chunk_size = int(sample_rate * chunk_duration)

        while self.is_listening:
            try:
                # Record a short chunk
                audio = sd.rec(
                    chunk_size,
                    samplerate=sample_rate,
                    channels=1,
                    dtype="float32",
                )
                sd.wait()

                # Simple VAD: check if audio has enough energy
                energy = np.sqrt(np.mean(audio**2))
                if energy < self.sensitivity:
                    continue

                # Transcribe the chunk
                from voice.stt import transcribe_audio_data
                text = transcribe_audio_data(audio.flatten(), sample_rate)

                if self.wake_phrase in text.lower():
                    logger.info(f"Wake word detected! Text: {text}")
                    if self.callback:
                        # Extract command after wake word
                        idx = text.lower().find(self.wake_phrase)
                        command = text[idx + len(self.wake_phrase):].strip()
                        self.callback(command if command else None)

            except Exception as e:
                logger.error(f"Wake word error: {e}")
                time.sleep(1)

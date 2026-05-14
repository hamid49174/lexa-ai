"""Lexa AI — Wake Word Detector v2
Listens for "Lexa" wake phrases and triggers conversation.
Delegates conversation logic to ConversationEngine.
"""

import logging
import threading
import time
import numpy as np
from typing import Optional, Callable

from voice.config import (
    SAMPLE_RATE, VAD_CHUNK_SAMPLES,
    WAKE_PHRASES, WAKE_COOLDOWN_S, WAKE_WINDOW_S,
    LISTEN_TIMEOUT_S, MAX_UTTERANCE_S,
)
from voice.vad import calibrate_noise_floor
from voice.conversation import ConversationEngine
from voice.playback import AudioPlayer

logger = logging.getLogger("lexa.wakeword")


class WakeWordDetector:
    """Listens for wake phrases and triggers conversation.

    Public API:
      - start()         → begin listening for wake word
      - start_direct()  → skip wake word, immediately start conversation
      - stop()          → stop everything
    """

    def __init__(self, wake_phrases=None, on_command=None, on_wake=None, on_chat=None):
        self.wake_phrases = [p.lower() for p in (wake_phrases or WAKE_PHRASES)]
        self.on_command = on_command
        self.on_wake = on_wake
        self.on_chat = on_chat
        self.is_listening = False
        self._thread: Optional[threading.Thread] = None
        self.sensitivity = 0.003
        self._noise_floor = 0.0
        self._last_wake = 0.0
        self._in_conversation = False

        # Conversation engine (created on demand)
        self._conversation: Optional[ConversationEngine] = None

        # External callbacks (set by router_voice.py)
        self._on_conversation_state: Optional[Callable] = None
        self._on_volume: Optional[Callable] = None

    # ── Public API ────────────────────────────────

    def start(self):
        if self.is_listening:
            return
        self.is_listening = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info("[Voice] Wake word detector started")

    def start_direct(self):
        if self.is_listening:
            return
        self.is_listening = True
        self._thread = threading.Thread(target=self._direct_conversation, daemon=True)
        self._thread.start()
        logger.info("[Voice] Direct conversation started")

    def stop(self):
        self.is_listening = False
        self._in_conversation = False
        if self._conversation:
            self._conversation.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        logger.info("[Voice] Stopped")

    @property
    def status(self):
        return {
            "active": self.is_listening,
            "in_conversation": self._in_conversation,
            "phrases": self.wake_phrases[:5],
            "sensitivity": self.sensitivity,
        }

    # ── Internal ──────────────────────────────────

    def _get_conversation_engine(self) -> ConversationEngine:
        """Create or return ConversationEngine with current callbacks."""
        player = AudioPlayer(on_volume=self._on_volume)
        self._conversation = ConversationEngine(
            player=player,
            on_state=self._on_conversation_state,
            on_volume=self._on_volume,
        )
        return self._conversation

    def _listen_loop(self):
        """Main wake word detection loop. Runs in daemon thread."""
        try:
            import sounddevice as sd
        except ImportError:
            logger.error("[Voice] sounddevice not installed")
            self.is_listening = False
            return

        # Calibrate
        self._noise_floor, self.sensitivity = calibrate_noise_floor(sd)

        while self.is_listening:
            try:
                audio = self._record_wake_window(sd)
                if audio is None:
                    continue

                from voice.stt import fast_transcribe
                text = fast_transcribe(audio, SAMPLE_RATE).lower().strip()
                if not text:
                    continue

                if not any(p in text for p in self.wake_phrases):
                    continue

                now = time.time()
                if now - self._last_wake < WAKE_COOLDOWN_S:
                    continue
                self._last_wake = now

                logger.info(f"[Wake] Detected: '{text}'")
                if self.on_wake:
                    self.on_wake()

                # Record command after wake word
                from backend.voice_ws import push_state
                push_state("listening")

                engine = self._get_conversation_engine()
                engine._noise_floor = self._noise_floor
                cmd_audio = engine._record_utterance(
                    sd, self._noise_floor,
                    is_listening=lambda: self.is_listening,
                    timeout_s=5, max_s=MAX_UTTERANCE_S,
                )
                if cmd_audio is None:
                    continue

                from voice.stt import transcribe_audio_data
                command = transcribe_audio_data(cmd_audio, SAMPLE_RATE).strip()
                logger.info(f"[Wake] Command: '{command}'")

                if command and self.on_chat:
                    self._in_conversation = True
                    engine.run_conversation(
                        command, sd,
                        is_listening=lambda: self.is_listening,
                    )
                    self._in_conversation = False
                elif command and self.on_command:
                    self.on_command(command)

            except Exception as e:
                logger.error(f"[Wake] Listen error: {e}", exc_info=True)
                time.sleep(2)

    def _direct_conversation(self):
        """Start conversation immediately (orb click, no wake word)."""
        try:
            import sounddevice as sd
        except ImportError:
            self.is_listening = False
            return

        self._noise_floor, self.sensitivity = calibrate_noise_floor(sd)
        self._in_conversation = True

        from backend.voice_ws import push_state
        push_state("conversation_start")
        push_state("listening")

        engine = self._get_conversation_engine()
        engine._noise_floor = self._noise_floor
        cmd_audio = engine._record_utterance(
            sd, self._noise_floor,
            is_listening=lambda: self.is_listening,
            timeout_s=LISTEN_TIMEOUT_S,
        )

        if cmd_audio is None:
            push_state("conversation_end")
            self._in_conversation = False
            self.is_listening = False
            return

        from voice.stt import transcribe_audio_data
        command = transcribe_audio_data(cmd_audio, SAMPLE_RATE).strip()
        logger.info(f"[Direct] Command: '{command}'")

        if command and self.on_chat:
            engine.run_conversation(
                command, sd,
                is_listening=lambda: self.is_listening,
            )
        else:
            push_state("conversation_end")

        self._in_conversation = False
        if self._on_volume:
            self._on_volume(0)
        self.is_listening = False

    def _record_wake_window(self, sd) -> Optional[np.ndarray]:
        """Record a sliding window for wake word detection."""
        sr = SAMPLE_RATE
        window_samples = int(WAKE_WINDOW_S * sr)
        chunk_samples = VAD_CHUNK_SAMPLES
        chunks_needed = window_samples // chunk_samples

        audio_chunks = []
        peak_rms = 0.0
        start_time = time.time()

        for _ in range(chunks_needed):
            if not self.is_listening or self._in_conversation:
                return None
            if time.time() - start_time > 5.0:
                return None
            try:
                chunk = sd.rec(chunk_samples, samplerate=sr, channels=1, dtype="float32")
                sd.wait()
            except Exception:
                return None

            flat = chunk.flatten()
            audio_chunks.append(flat)
            rms = np.sqrt(np.mean(flat ** 2))
            if self._on_volume:
                self._on_volume(rms)
            if rms > peak_rms:
                peak_rms = rms

        if peak_rms < self.sensitivity:
            return None

        return np.concatenate(audio_chunks)

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
    WAKE_FALLBACK_STT_MIN_INTERVAL_S, WAKE_FALLBACK_STT_MAX_INTERVAL_S,
    WAKE_FALLBACK_STT_BACKOFF_STEP_S,
)
from voice.vad import calibrate_noise_floor
from voice.conversation import ConversationEngine
from voice.playback import AudioPlayer
from voice.wakeword_engines import (
    WakeWordEngine,
    create_default_wakeword_engine,
    _command_after_wake_phrase,
    _contains_wake_phrase,
)

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
        self._wake_engine: WakeWordEngine = create_default_wakeword_engine()
        self.is_listening = False
        self._thread: Optional[threading.Thread] = None
        self.sensitivity = 0.003
        self._noise_floor = 0.0
        self._last_wake = 0.0
        self._in_conversation = False
        self._ready = False
        self._last_error = ""
        self._startup_event = threading.Event()
        self._last_transcript = ""
        self._last_detected_text = ""
        self._last_command = ""
        self._last_command_source = ""
        self._last_window_rms = 0.0
        self._wake_checks = 0
        self._stt_checks = 0
        self._skipped_stt_checks = 0
        self._last_stt_check_at = 0.0
        self._fallback_stt_interval_s = float(WAKE_FALLBACK_STT_MIN_INTERVAL_S)
        self._non_wake_transcripts = 0
        self._last_heard_at = 0.0
        self._last_detected_at = 0.0

        # Conversation engine (created on demand)
        self._conversation: Optional[ConversationEngine] = None

        # External callbacks (set by router_voice.py)
        self._on_conversation_state: Optional[Callable] = None
        self._on_volume: Optional[Callable] = None

    # ── Public API ────────────────────────────────

    def start(self, wait_ready_s: float = 0.0):
        if self.is_listening:
            return self.status
        self._ready = False
        self._last_error = ""
        self._startup_event.clear()
        self.is_listening = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        if wait_ready_s and wait_ready_s > 0:
            self._startup_event.wait(timeout=wait_ready_s)
        logger.info("[Voice] Wake word detector started")
        return self.status

    def start_direct(self, wait_ready_s: float = 0.0):
        if self.is_listening:
            return self.status
        self._ready = False
        self._last_error = ""
        self._startup_event.clear()
        self.is_listening = True
        self._thread = threading.Thread(target=self._direct_conversation, daemon=True)
        self._thread.start()
        if wait_ready_s and wait_ready_s > 0:
            self._startup_event.wait(timeout=wait_ready_s)
        logger.info("[Voice] Direct conversation started")
        return self.status

    def stop(self):
        self.is_listening = False
        self._in_conversation = False
        self._ready = False
        if self._conversation:
            self._conversation.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        logger.info("[Voice] Stopped")

    @property
    def status(self):
        thread_alive = bool(self._thread and self._thread.is_alive())
        return {
            "active": bool(self.is_listening and thread_alive),
            "ready": bool(self.is_listening and self._ready and thread_alive),
            "in_conversation": self._in_conversation,
            "phrases": list(self.wake_phrases),
            "sensitivity": float(self.sensitivity or 0.0),
            "thread_alive": thread_alive,
            "error": self._last_error,
            "last_transcript": self._last_transcript,
            "last_detected_text": self._last_detected_text,
            "last_command": self._last_command,
            "last_command_source": self._last_command_source,
            "last_window_rms": round(float(self._last_window_rms or 0.0), 6),
            "wake_checks": self._wake_checks,
            "stt_checks": self._stt_checks,
            "skipped_stt_checks": self._skipped_stt_checks,
            "fallback_stt_min_interval_s": float(WAKE_FALLBACK_STT_MIN_INTERVAL_S),
            "fallback_stt_max_interval_s": float(WAKE_FALLBACK_STT_MAX_INTERVAL_S),
            "fallback_stt_interval_s": round(float(self._fallback_stt_interval_s), 2),
            "non_wake_transcripts": self._non_wake_transcripts,
            "last_heard_at": self._last_heard_at,
            "last_detected_at": self._last_detected_at,
            "wake_engine": self._wake_engine.status(),
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

    def _mark_unavailable(self, message: str):
        self._last_error = message
        self._ready = False
        self.is_listening = False
        self._startup_event.set()

    def _prepare_wake_engine(self) -> bool:
        ensure_ready = getattr(self._wake_engine, "ensure_ready", None)
        if callable(ensure_ready):
            ensure_ready()
        status = self._wake_engine.status()
        if status.get("ready"):
            return True
        error = status.get("error") or status.get("detail") or "Wake Word engine is not ready."
        self._mark_unavailable(str(error))
        return False

    def _finish_wake_without_command(self, message: str = "No command heard after wake word."):
        from backend.voice_ws import push_event, push_state

        self._last_command = ""
        push_event("wake_timeout", message)
        push_state("conversation_end")
        if self._on_volume:
            self._on_volume(0)
        try:
            from backend.voice_ws import push_error
            push_error(message)
        except Exception:
            pass

    def _listen_loop(self):
        """Main wake word detection loop. Runs in daemon thread."""
        try:
            import sounddevice as sd
        except ImportError:
            logger.error("[Voice] sounddevice not installed")
            self._mark_unavailable("sounddevice nicht installiert.")
            return

        if not self._prepare_wake_engine():
            logger.error("[Voice] Wake word engine unavailable: %s", self._last_error)
            return

        try:
            self._noise_floor, self.sensitivity = calibrate_noise_floor(sd)
            self._ready = True
            self._startup_event.set()
        except Exception as e:
            logger.error(f"[Voice] Wake word calibration failed: {e}", exc_info=True)
            self._mark_unavailable(f"Mikrofon-Kalibrierung fehlgeschlagen: {e}")
            return

        while self.is_listening:
            try:
                audio = self._record_wake_window(sd)
                if audio is None:
                    continue

                wake_engine_status = self._wake_engine.status()
                if wake_engine_status.get("uses_stt"):
                    now = time.time()
                    if now - self._last_stt_check_at < self._fallback_stt_interval_s:
                        self._skipped_stt_checks += 1
                        continue
                    self._last_stt_check_at = now
                    self._stt_checks += 1
                detection = self._wake_engine.detect(audio, SAMPLE_RATE, self.wake_phrases)
                self._last_error = ""
                if detection.detail.get("error"):
                    self._last_error = str(detection.detail.get("error"))

                text = (detection.text or "").lower().strip()
                if not text:
                    continue

                self._last_transcript = text[:160]
                self._last_heard_at = time.time()
                if not detection.detected and not _contains_wake_phrase(text, self.wake_phrases):
                    self._record_non_wake_transcript()
                    continue

                self._reset_fallback_stt_backoff()

                now = time.time()
                if now - self._last_wake < WAKE_COOLDOWN_S:
                    continue
                self._last_wake = now
                self._last_detected_text = text[:160]
                self._last_detected_at = now

                logger.info(f"[Wake] Detected: '{text}'")
                if self.on_wake:
                    self.on_wake()

                inline_command = detection.command or _command_after_wake_phrase(text, self.wake_phrases)
                if inline_command:
                    command = inline_command
                    self._last_command_source = detection.source or "wake_window"
                else:
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
                        self._finish_wake_without_command()
                        continue

                    from voice.stt import transcribe_audio_data
                    command = transcribe_audio_data(cmd_audio, SAMPLE_RATE).strip()
                    self._last_command_source = "post_wake_recording"
                logger.info(f"[Wake] Command: '{command}'")
                self._last_command = command[:160]

                if not command:
                    self._finish_wake_without_command()
                    continue

                if command and self.on_chat:
                    engine = self._get_conversation_engine()
                    engine._noise_floor = self._noise_floor
                    self._in_conversation = True
                    engine.run_conversation(
                        command, sd,
                        is_listening=lambda: self.is_listening,
                    )
                    self._in_conversation = False
                elif command and self.on_command:
                    self.on_command(command)

            except Exception as e:
                self._last_error = str(e)
                logger.error(f"[Wake] Listen error: {e}", exc_info=True)
                time.sleep(2)

    def _direct_conversation(self):
        """Start conversation immediately (orb click, no wake word)."""
        try:
            import sounddevice as sd
        except ImportError:
            self._mark_unavailable("sounddevice nicht installiert.")
            return

        try:
            self._noise_floor, self.sensitivity = calibrate_noise_floor(sd)
            self._ready = True
            self._startup_event.set()
        except Exception as e:
            logger.error(f"[Voice] Direct conversation calibration failed: {e}", exc_info=True)
            self._mark_unavailable(f"Mikrofon-Kalibrierung fehlgeschlagen: {e}")
            return
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
        if not self.is_listening or self._in_conversation:
            return None
        try:
            audio = sd.rec(window_samples, samplerate=sr, channels=1, dtype="float32")
            sd.wait()
        except Exception as e:
            self._last_error = f"Audioaufnahme fehlgeschlagen: {e}"
            return None

        if not self.is_listening or self._in_conversation:
            return None

        flat = audio.flatten()
        peak_rms = float(np.sqrt(np.mean(flat ** 2))) if len(flat) else 0.0
        self._wake_checks += 1
        self._last_window_rms = peak_rms
        if self._on_volume:
            self._on_volume(peak_rms)

        wake_engine_status = self._wake_engine.status()
        if wake_engine_status.get("uses_stt") and peak_rms < self.sensitivity:
            return None

        return flat

    def _record_non_wake_transcript(self):
        self._non_wake_transcripts += 1
        if not self._wake_engine.status().get("uses_stt"):
            return
        self._fallback_stt_interval_s = min(
            float(WAKE_FALLBACK_STT_MAX_INTERVAL_S),
            float(self._fallback_stt_interval_s) + float(WAKE_FALLBACK_STT_BACKOFF_STEP_S),
        )

    def _reset_fallback_stt_backoff(self):
        self._non_wake_transcripts = 0
        self._fallback_stt_interval_s = float(WAKE_FALLBACK_STT_MIN_INTERVAL_S)

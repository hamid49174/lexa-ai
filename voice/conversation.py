"""Lexa AI — Conversation Engine v2
Multi-turn voice conversation with streaming AI → sentence TTS pipeline.
Handles tool calls, barge-in, and conversation history.
"""

import collections
import concurrent.futures
import logging
import re
import time
from typing import Optional, Callable

from voice.config import EXIT_PHRASES
from voice.playback import AudioPlayer

logger = logging.getLogger("lexa.conversation")


def _safe_log_token(value: object, *, fallback: str = "unknown") -> str:
    text = "".join(ch for ch in str(value or "") if ch.isalnum() or ch in "._:-").strip("._:-")
    return (text[:64] or fallback)


def _log_conversation_text_event(label: str, text: object, **metadata: object) -> None:
    fields = [f"textChars={len(str(text or ''))}"]
    for key, value in metadata.items():
        fields.append(f"{_safe_log_token(key, fallback='field')}={_safe_log_token(value)}")
    logger.info("[%s] %s", label, " ".join(fields))

# Sentence boundary pattern
_SENTENCE_END = re.compile(r'(?<=[.!?])\s+|(?<=\n)')

# Shared TTS thread pool (reused across turns)
_tts_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="tts",
)


def _split_into_sentences(text: str) -> list[str]:
    parts = _SENTENCE_END.split(text)
    return [p.strip() for p in parts if p and len(p.strip()) >= 3]


def _is_exit(text: str) -> bool:
    if not text:
        return False
    clean = text.lower().strip().rstrip(".!?")
    if not clean:
        return False
    # Exact match on the whole utterance always counts as exit.
    if clean in EXIT_PHRASES:
        return True
    # For multi-word phrases ("bis später", "das wars") allow a word-boundary
    # substring match. Single-token phrases ("stop", "halt", "ende", "bye")
    # must NOT match as substrings — otherwise "Halterung", "Endergebnis" etc.
    # would falsely terminate the conversation.
    for phrase in EXIT_PHRASES:
        if " " in phrase and re.search(r"\b" + re.escape(phrase) + r"\b", clean):
            return True
    return False


def _clean_for_tts(text: str) -> str:
    """Strip markdown and non-speakable content for TTS."""
    # Strip markdown code blocks (```...```)
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Strip inline code (`...`)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    # Strip URLs
    text = re.sub(r'https?://\S+', '', text)
    # Strip markdown headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Strip bold/italic markers
    text = re.sub(r'\*\*([^*]*)\*\*', r'\1', text)
    text = re.sub(r'__([^_]*)__', r'\1', text)
    text = re.sub(r'\*([^*]*)\*', r'\1', text)
    text = re.sub(r'_([^_]*)_', r'\1', text)
    # Convert bullet points to natural pauses — only when a word follows the
    # marker, so number/sign lines like "-5 Grad" or "- 20 % Rabatt" keep their
    # content instead of becoming ". 5 Grad".
    text = re.sub(r'^\s*[-*]\s+(?=[A-Za-zÄÖÜäöüß])', '. ', text, flags=re.MULTILINE)
    # Strip remaining markdown artifacts (e.g. horizontal rules)
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
    # Collapse whitespace
    text = re.sub(r'\n{2,}', '. ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def _tts_for_text(text: str) -> str | None:
    """Generate TTS audio file for text. Returns path or None."""
    try:
        from voice.tts import speak
        cleaned = _clean_for_tts(text)
        if not cleaned:
            return None
        return speak(cleaned)
    except Exception as e:
        logger.warning(f"[Conv] TTS failed: {e}")
        return None


def _collect_tts_results(futures: list[concurrent.futures.Future],
                         timeout: float = 30.0) -> list[str]:
    """Collect TTS results from futures in order."""
    paths = []
    for i, future in enumerate(futures):
        try:
            path = future.result(timeout=timeout)
            if path:
                paths.append(path)
        except concurrent.futures.TimeoutError:
            logger.error(f"[Conv] TTS {i + 1}/{len(futures)} timed out")
        except concurrent.futures.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[Conv] TTS {i + 1}/{len(futures)} failed: {e}")
    return paths


def _extract_tool_result(exec_result: dict, action_name: str) -> str:
    """Extract human-readable text from tool execution result."""
    if not exec_result.get("success"):
        return exec_result.get("error", f"{action_name} fehlgeschlagen.")
    data = exec_result.get("data")
    if not data:
        return f"{action_name} erledigt."
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("summary", "message", "error"):
            if key in data:
                return str(data[key])
        return ". ".join(
            f"{k}: {v}" for k, v in data.items()
            if v and k not in ("icon", "icon_code", "will_rain")
        ) or f"{action_name} erledigt."
    return str(data)


def _handle_tool_call(tool_call_result: dict, full_text: str,
                      command_text: str, source: str = "voice") -> tuple[str, list[str]]:
    """Handle AI tool call: parse, execute, extract result, generate TTS."""
    from backend.action_parser import process_tool_call
    reply, action, requires_confirmation = process_tool_call(
        tool_call_result.get("tool_calls", []),
        ai_message=full_text,
        source=source,
    )

    audio_paths = []

    if action and not requires_confirmation:
        from backend.action_executor import execute_action
        exec_result = execute_action(action, source=source)
        reply = _extract_tool_result(exec_result, action["action"])
        logger.info(f"[Conv] Tool {action['action']} -> {reply[:100]}")
    elif action and requires_confirmation:
        reply = f"Soll ich '{action['action']}' wirklich ausfuehren? Das erfordert eine Bestaetigung."

    if reply:
        from backend.voice_ws import push_response_chunk
        push_response_chunk(reply)
        path = _tts_for_text(reply)
        if path:
            audio_paths.append(path)

    return reply or full_text, audio_paths


# Words/markers that end a heuristically extracted argument phrase, so a
# follow-up clause ("Word und schreibe einen Brief") is not swallowed.
_ARG_STOP_WORDS = {"und", "dann", "danach", "sowie", "oder", "bitte"}


def _extract_arg_phrase(words: list[str], start: int) -> str:
    """Collect words from `start` until a stop word or sentence punctuation."""
    collected: list[str] = []
    for w in words[start:]:
        if w.lower() in _ARG_STOP_WORDS:
            break
        # Stop at clause/sentence punctuation but keep the leading token.
        cut = re.split(r"[,.;:!?]", w, maxsplit=1)[0]
        if cut:
            collected.append(cut)
        if cut != w:  # punctuation was hit inside this token
            break
    return " ".join(collected).strip()


def _detect_text_tool_call(full_text: str, command_text: str) -> tuple[str, list[str]] | None:
    """Detect when AI described a tool call in text instead of making one."""
    patterns = [
        re.compile(r"[Ff]ühre\s+['\"]?(\w+)['\"]?\s+aus"),
        re.compile(r"[Ss]tarte\s+['\"]?(\w+)['\"]?"),
        re.compile(r"[Rr]ufe\s+['\"]?(\w+)['\"]?\s+auf"),
    ]

    for pat in patterns:
        m = pat.search(full_text)
        if not m:
            continue
        tool_name = m.group(1)
        try:
            from backend.tool_registry import get_tool_names, get_tool
            if tool_name not in get_tool_names():
                continue

            logger.warning(f"[Conv] AI described tool '{tool_name}' as text — executing fallback")
            args = {}
            schema = get_tool(tool_name)
            if schema and "parameters" in schema.get("function", {}):
                props = schema["function"]["parameters"].get("properties", {})
                words = command_text.split()
                lower_words = command_text.lower().split()
                if "city" in props:
                    for i, w in enumerate(lower_words):
                        if w in ("in", "für", "von") and i + 1 < len(words):
                            phrase = _extract_arg_phrase(words, i + 1)
                            if phrase:
                                args["city"] = phrase
                            break
                if "name" in props:
                    for trigger in ("öffne", "starte", "open", "start"):
                        if trigger in lower_words:
                            idx = lower_words.index(trigger)
                            if idx + 1 < len(words):
                                phrase = _extract_arg_phrase(words, idx + 1)
                                if phrase:
                                    args["name"] = phrase
                            break

            from backend.action_parser import process_tool_call
            synthetic_tc = [{"id": "fallback", "name": tool_name, "arguments": args}]
            reply, action, requires_confirmation = process_tool_call(
                synthetic_tc, ai_message=full_text, source="voice_fallback",
            )
            if action and not requires_confirmation:
                from backend.action_executor import execute_action
                exec_result = execute_action(action, source="voice_fallback")
                reply = _extract_tool_result(exec_result, action["action"])
                audio_paths = []
                path = _tts_for_text(reply)
                if path:
                    audio_paths.append(path)
                return reply, audio_paths
        except ImportError:
            pass

    return None


class ConversationEngine:
    """Multi-turn voice conversation — ChatGPT Voice style.

    Handles the streaming AI → sentence split → TTS → playback pipeline.
    Tool call detection and execution included.
    """

    def __init__(self, player: Optional[AudioPlayer] = None,
                 on_state: Optional[Callable[[str], None]] = None,
                 on_volume: Optional[Callable[[float], None]] = None):
        self.player = player or AudioPlayer()
        self._on_state = on_state
        self._on_volume = on_volume
        self._active = False
        self._noise_floor = 0.0
        # Cap kept even so the history always holds whole user/assistant pairs.
        # Trimming happens manually (see _append_turn) to never leave a dangling
        # entry that some LLM APIs reject as an invalid role sequence.
        self._history_max = 20
        self._history: collections.deque = collections.deque()

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    def stop(self):
        self._active = False
        self.player.stop()

    def _append_turn(self, user_text: str, assistant_text: str) -> None:
        """Append a user/assistant turn and trim by whole pairs.

        Trims two entries at a time so the history never starts with a dangling
        assistant message or ends with an orphaned user message.
        """
        self._history.append({"role": "user", "content": user_text})
        if assistant_text:
            self._history.append({"role": "assistant", "content": assistant_text})
        while len(self._history) > self._history_max:
            self._history.popleft()
            if self._history and self._history[0]["role"] == "assistant":
                self._history.popleft()

    def _push_state(self, state: str):
        if self._on_state:
            try:
                self._on_state(state)
            except Exception:
                pass

    def run_single_turn(self, command_text: str,
                        conversation_history: list = None) -> dict | None:
        """Single conversation turn (for HTTP API and voice loop).
        Returns {reply, audio_paths} or None."""
        if not command_text or not command_text.strip():
            return None

        from backend.voice_ws import push_command, push_state, push_response, push_response_chunk, push_event
        from backend.security import audit_log

        push_command(command_text)
        push_state("processing")

        try:
            from backend.ai_engine import chat_stream
            full_text = ""
            sentence_buffer = ""
            sentence_count = 0
            tool_call_result = None
            t0 = time.time()
            first_response_sent = False

            for chunk in chat_stream(command_text, conversation_history=conversation_history):
                if isinstance(chunk, dict) and chunk.get("type") == "tool_call":
                    tool_call_result = chunk
                    break
                if not isinstance(chunk, str):
                    continue

                full_text += chunk
                sentence_buffer += chunk

                sentences = _split_into_sentences(sentence_buffer)
                if len(sentences) > 1:
                    for sent in sentences[:-1]:
                        sentence_count += 1
                        push_response_chunk(sent)
                        if not first_response_sent:
                            first_response_sent = True
                            latency_ms = int((time.time() - t0) * 1000)
                            logger.info(f"[Conv] First text latency: {latency_ms}ms")
                            push_event("latency", "", ms=latency_ms)
                    sentence_buffer = sentences[-1]

            # Handle tool calls
            if tool_call_result is not None:
                audio_paths = []
                reply, tool_audio = _handle_tool_call(
                    tool_call_result, full_text, command_text, source="voice_stream",
                )
                audio_paths.extend(tool_audio)
                push_response(reply, tts_handled=True)
                audit_log("voice", "tool_call", f"reply={reply[:80]}")
                return {"reply": reply, "audio_paths": audio_paths}

            # Detect text-described tool calls
            if full_text:
                fallback = _detect_text_tool_call(full_text, command_text)
                if fallback:
                    reply, fb_audio = fallback
                    push_response(reply, tts_handled=True)
                    return {"reply": reply, "audio_paths": fb_audio}

            # Flush remaining buffer (last sentence without trailing punctuation)
            remaining = sentence_buffer.strip()
            if remaining:
                sentence_count += 1
                push_response_chunk(remaining)

            # One TTS file per voice turn: synthesize the full reply text once.
            audio_paths = []
            path = _tts_for_text(full_text)
            if path:
                audio_paths.append(path)
            push_response(full_text, tts_handled=True)
            audit_log("voice", "stream_done", f"sentences={sentence_count}")
            logger.info(f"[Conv] Done — {sentence_count} sentences, {len(audio_paths)} audio")
            return {"reply": full_text, "audio_paths": audio_paths}

        except Exception as e:
            logger.error(f"[Conv] Error: {e}", exc_info=True)
            # Legacy fallback
            try:
                return self._turn_legacy(command_text, conversation_history)
            except Exception as fb_err:
                logger.error(f"[Conv] Legacy fallback failed: {fb_err}", exc_info=True)
                from backend.voice_ws import push_error
                push_error("KI-Verarbeitung fehlgeschlagen.")
                return None

    def _turn_legacy(self, command_text: str,
                     conversation_history: list = None) -> dict | None:
        """Non-streaming fallback."""
        from backend.voice_ws import push_command, push_state, push_response
        push_command(command_text)
        push_state("processing")

        from backend.ai_engine import chat as ai_chat
        ai_result = ai_chat(command_text, conversation_history=conversation_history)

        reply = ""
        if isinstance(ai_result, dict) and ai_result.get("type") == "tool_call":
            reply, _ = _handle_tool_call(ai_result, "", command_text, source="voice_legacy")
        elif isinstance(ai_result, dict):
            reply = ai_result.get("content", str(ai_result))
        else:
            reply = str(ai_result)

        push_response(reply, tts_handled=True)
        audio_path = _tts_for_text(reply)
        return {"reply": reply, "audio_paths": [audio_path] if audio_path else []}

    def run_conversation(self, initial_command: str, sd,
                         is_listening: Callable[[], bool]) -> None:
        """Multi-turn conversation loop until exit phrase or timeout."""
        from voice.stt import transcribe_audio_data
        from voice.vad import calibrate_noise_floor
        from voice.config import (
            SAMPLE_RATE, LISTEN_TIMEOUT_S, MAX_UTTERANCE_S,
        )
        from backend.voice_ws import push_state, push_response_chunk

        self._active = True
        command = initial_command
        turn = 0
        noise_floor = 0.0001
        empty_retries = 0
        MAX_EMPTY_RETRIES = 1

        # Try to calibrate (may already be done by wakeword)
        try:
            noise_floor, _ = calibrate_noise_floor(sd)
        except Exception:
            pass

        # Keep the freshly calibrated noise floor as the engine-wide value so
        # the barge-in threshold (play_files_with_bargein uses self._noise_floor)
        # stays consistent with _record_utterance, which gets noise_floor directly.
        if noise_floor:
            self._noise_floor = noise_floor

        push_state("conversation_start")

        while is_listening() and self._active:
            turn += 1

            if _is_exit(command):
                _log_conversation_text_event("Conv Exit phrase", command, turn=turn)
                push_state("conversation_end")
                break

            if not command or not command.strip():
                push_state("conversation_end")
                break

            # AI Turn
            push_state("processing")
            result = self.run_single_turn(command, conversation_history=list(self._history))

            if result is None:
                push_state("conversation_end")
                break

            # Update history (trimmed by whole user/assistant pairs)
            ai_reply = result.get("reply", "")
            self._append_turn(command, ai_reply)

            # Playback with barge-in
            audio_paths = result.get("audio_paths") or []

            if audio_paths:
                push_state("speaking")
                bargein_audio = self.player.play_files_with_bargein(
                    audio_paths, sd,
                    is_active=lambda: is_listening() and self._active,
                    noise_floor=self._noise_floor,
                )

                if bargein_audio is not None:
                    logger.info("[Conv] Barge-in detected")
                    push_state("bargein")
                    if self._history and self._history[-1]["role"] == "assistant":
                        self._history[-1]["content"] += " [unterbrochen]"

                    command = transcribe_audio_data(bargein_audio, SAMPLE_RATE).strip()
                    if command:
                        _log_conversation_text_event("Conv Barge-in transcript", command, turn=turn)
                        continue
            else:
                time.sleep(0.2)

            # Listen for next turn
            push_state("listening")
            cmd_audio = self._record_utterance(
                sd, noise_floor, is_listening,
                timeout_s=LISTEN_TIMEOUT_S, max_s=MAX_UTTERANCE_S,
            )

            if cmd_audio is None:
                logger.info("[Conv] Silence timeout — ending conversation")
                push_state("conversation_end")
                break

            command = transcribe_audio_data(cmd_audio, SAMPLE_RATE).strip()
            _log_conversation_text_event("Conv Turn input", command, turn=turn)

            # Empty transcript (STT failure / unintelligible) — ask the user to
            # repeat once instead of silently ending the conversation. After the
            # retry limit, fall through so the empty-command guard ends the loop.
            if not command and empty_retries < MAX_EMPTY_RETRIES:
                empty_retries += 1
                logger.info("[Conv] Empty transcript — asking user to repeat")
                clarify = "Entschuldigung, das habe ich nicht verstanden. Kannst du das wiederholen?"
                push_response_chunk(clarify)
                clarify_path = _tts_for_text(clarify)
                if clarify_path:
                    push_state("speaking")
                    self.player.play_files_with_bargein(
                        [clarify_path], sd,
                        is_active=lambda: is_listening() and self._active,
                        noise_floor=self._noise_floor,
                    )
                push_state("listening")
                cmd_audio = self._record_utterance(
                    sd, noise_floor, is_listening,
                    timeout_s=LISTEN_TIMEOUT_S, max_s=MAX_UTTERANCE_S,
                )
                if cmd_audio is None:
                    push_state("conversation_end")
                    break
                command = transcribe_audio_data(cmd_audio, SAMPLE_RATE).strip()
                _log_conversation_text_event("Conv Turn retry input", command, turn=turn)
            elif command:
                empty_retries = 0

        self._active = False
        if self._on_volume:
            self._on_volume(0)

    def _record_utterance(self, sd, noise_floor: float,
                          is_listening: Callable[[], bool],
                          timeout_s: float = 15, max_s: float = 25):
        """Record a single utterance with relative energy VAD."""
        import numpy as np
        from voice.vad import is_speech, reset as vad_reset
        from voice.config import (
            SAMPLE_RATE, VAD_CHUNK_SAMPLES, RECORD_CHUNK_MS,
            SILENCE_MS_BASE, MIN_SPEECH_MS, PRE_SPEECH_CHUNKS,
        )

        sr = SAMPLE_RATE
        chunk_samples = VAD_CHUNK_SAMPLES
        chunks_per_second = sr // chunk_samples

        pre_buffer = collections.deque(maxlen=PRE_SPEECH_CHUNKS)
        speech_started = False
        speech_chunks: list[np.ndarray] = []
        silence_chunks = 0
        total_chunks = 0
        max_chunks = int(max_s * chunks_per_second)
        timeout_chunks = int(timeout_s * chunks_per_second)
        silence_needed = int(SILENCE_MS_BASE / RECORD_CHUNK_MS)
        peak_rms = 0.0

        vad_reset()
        abs_start = time.time()
        abs_max = max_s + timeout_s + 5

        try:
            with sd.InputStream(samplerate=sr, channels=1, dtype="float32", blocksize=chunk_samples) as stream:
                while is_listening() and self._active:
                    if time.time() - abs_start > abs_max:
                        break

                    try:
                        chunk, _overflowed = stream.read(chunk_samples)
                    except Exception:
                        return None

                    if not is_listening() or not self._active:
                        return None

                    flat = chunk.flatten()
                    total_chunks += 1
                    rms = np.sqrt(np.mean(flat ** 2))

                    if self._on_volume:
                        self._on_volume(rms)

                    if rms > peak_rms:
                        peak_rms = rms

                    speech = is_speech(flat, peak_rms=peak_rms, noise_floor=noise_floor)

                    if not speech_started:
                        pre_buffer.append(flat)
                        if speech:
                            speech_started = True
                            for pre_chunk in pre_buffer:
                                speech_chunks.append(pre_chunk)
                            speech_chunks.append(flat)
                            silence_chunks = 0
                        elif total_chunks >= timeout_chunks:
                            return None
                    else:
                        speech_chunks.append(flat)
                        if speech:
                            silence_chunks = 0
                        else:
                            silence_chunks += 1
                        if silence_chunks >= silence_needed:
                            duration_ms = len(speech_chunks) * RECORD_CHUNK_MS
                            if duration_ms >= MIN_SPEECH_MS:
                                break
                            else:
                                speech_started = False
                                speech_chunks.clear()
                                silence_chunks = 0
                        if total_chunks >= max_chunks:
                            break
        except Exception:
            return None

        if not speech_chunks:
            return None
        return np.concatenate(speech_chunks)

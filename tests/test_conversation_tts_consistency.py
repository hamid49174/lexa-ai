"""Regression tests for voice conversation TTS consistency."""

import logging
import sys
import types

from voice import conversation


def _module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def test_streaming_voice_turn_generates_one_tts_file(monkeypatch):
    ws_calls = []

    monkeypatch.setitem(sys.modules, "backend.voice_ws", _module(
        "backend.voice_ws",
        push_command=lambda text: ws_calls.append(("command", text)),
        push_state=lambda state: ws_calls.append(("state", state)),
        push_response=lambda text, tts_handled=False: ws_calls.append(("response", text, tts_handled)),
        push_response_chunk=lambda text: ws_calls.append(("chunk", text)),
        push_event=lambda *args, **kwargs: ws_calls.append(("event", args, kwargs)),
        push_error=lambda text: ws_calls.append(("error", text)),
    ))
    monkeypatch.setitem(sys.modules, "backend.security", _module(
        "backend.security",
        audit_log=lambda *args, **kwargs: ws_calls.append(("audit", args, kwargs)),
    ))
    monkeypatch.setitem(sys.modules, "backend.ai_engine", _module(
        "backend.ai_engine",
        chat_stream=lambda *args, **kwargs: iter(["Erster Satz. ", "Zweiter Satz."]),
    ))

    tts_calls = []

    def fake_tts(text):
        tts_calls.append(text)
        return "reply.mp3"

    monkeypatch.setattr(conversation, "_tts_for_text", fake_tts)

    engine = conversation.ConversationEngine()
    result = engine.run_single_turn("test")

    assert result == {
        "reply": "Erster Satz. Zweiter Satz.",
        "audio_paths": ["reply.mp3"],
    }
    assert tts_calls == ["Erster Satz. Zweiter Satz."]
    assert ("chunk", "Erster Satz.") in ws_calls
    assert ("chunk", "Zweiter Satz.") in ws_calls
    # Server hat Audio erzeugt -> Frontend soll NICHT zusaetzlich sprechen.
    assert ("response", "Erster Satz. Zweiter Satz.", True) in ws_calls


def test_streaming_voice_turn_tts_failure_lets_frontend_speak(monkeypatch):
    # Scan-Fix D: schlug Server-TTS fehl, blieb tts_handled=True haengen -> Stille.
    ws_calls = []

    monkeypatch.setitem(sys.modules, "backend.voice_ws", _module(
        "backend.voice_ws",
        push_command=lambda text: ws_calls.append(("command", text)),
        push_state=lambda state: ws_calls.append(("state", state)),
        push_response=lambda text, tts_handled=False: ws_calls.append(("response", text, tts_handled)),
        push_response_chunk=lambda text: ws_calls.append(("chunk", text)),
        push_event=lambda *args, **kwargs: ws_calls.append(("event", args, kwargs)),
        push_error=lambda text: ws_calls.append(("error", text)),
    ))
    monkeypatch.setitem(sys.modules, "backend.security", _module(
        "backend.security",
        audit_log=lambda *args, **kwargs: ws_calls.append(("audit", args, kwargs)),
    ))
    monkeypatch.setitem(sys.modules, "backend.ai_engine", _module(
        "backend.ai_engine",
        chat_stream=lambda *args, **kwargs: iter(["Nur ein Satz."]),
    ))
    monkeypatch.setattr(conversation, "_tts_for_text", lambda text: None)  # TTS scheitert

    engine = conversation.ConversationEngine()
    result = engine.run_single_turn("test")

    assert result == {"reply": "Nur ein Satz.", "audio_paths": []}
    # Kein Server-Audio -> tts_handled=False -> Frontend uebernimmt TTS.
    assert ("response", "Nur ein Satz.", False) in ws_calls


def test_conversation_text_event_log_redacts_transcript_text(caplog):
    secret_text = "Bitte merke dir token=supersecretvalue und sk-testsecret12345"

    caplog.set_level(logging.INFO, logger="lexa.conversation")
    conversation._log_conversation_text_event("Conv Turn input", secret_text, turn=2)

    logged = caplog.text
    assert "textChars=" in logged
    assert "turn=2" in logged
    assert "Bitte merke" not in logged
    assert "supersecretvalue" not in logged
    assert "sk-testsecret12345" not in logged

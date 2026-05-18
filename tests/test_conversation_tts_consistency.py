"""Regression tests for voice conversation TTS consistency."""

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

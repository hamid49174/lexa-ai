"""Regression tests for wake-word fast STT fallback behavior."""

import logging

import numpy as np

from voice import stt


def test_fast_transcribe_returns_empty_on_local_engine_error(monkeypatch):
    class BrokenModel:
        def transcribe(self, *args, **kwargs):
            raise RuntimeError("cublas64_12.dll is not found")

    monkeypatch.setattr(stt, "has_speech", lambda audio: True)
    monkeypatch.setattr(stt, "_cloud_transcribe", lambda *args, **kwargs: None)
    monkeypatch.setattr(stt, "_get_local_model", lambda: BrokenModel())

    text = stt.fast_transcribe(np.ones(1600, dtype=np.float32), sample_rate=16000)

    assert text == ""


def test_transcription_success_log_redacts_transcript_text(caplog):
    secret_text = "Mein API key ist sk-testsecret12345 und token=supersecretvalue"

    caplog.set_level(logging.INFO, logger="lexa.stt")
    stt._log_transcription_success("Deepgram", 123, secret_text)

    logged = caplog.text
    assert "textChars=" in logged
    assert str(len(secret_text)) in logged
    assert "Mein API key" not in logged
    assert "sk-testsecret12345" not in logged
    assert "supersecretvalue" not in logged

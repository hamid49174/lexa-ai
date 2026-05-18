"""Regression tests for wake-word fast STT fallback behavior."""

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

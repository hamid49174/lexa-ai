"""Regression tests for consistent TTS voice/provider selection."""

import asyncio
from pathlib import Path

import pytest

from voice import tts


@pytest.fixture(autouse=True)
def isolated_tts(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "AUDIO_CACHE_DIR", tmp_path)
    monkeypatch.setattr(tts, "_sapi_available", lambda: False)
    monkeypatch.setattr(tts, "_get_key", lambda provider: {
        "elevenlabs": "el-key",
        "cartesia": "cart-key",
    }.get(provider))
    monkeypatch.setattr(tts, "_elevenlabs_enabled", True)


def _write_audio(path: str, payload: bytes = b"audio") -> str:
    Path(path).write_bytes(payload)
    return path


def test_provider_cache_paths_do_not_collide():
    _, elevenlabs_path = tts._provider_cache_path("same text", "elevenlabs")
    _, cartesia_path = tts._provider_cache_path("same text", "cartesia")

    assert elevenlabs_path != cartesia_path
    assert elevenlabs_path.endswith(".mp3")
    assert cartesia_path.endswith(".mp3")


def test_provider_order_follows_configured_voice_preference(monkeypatch):
    monkeypatch.setattr(tts, "_get_key", lambda provider: {
        "openai": "oa-key",
        "elevenlabs": "el-key",
        "cartesia": "cart-key",
    }.get(provider))
    monkeypatch.setattr(tts, "_tts_provider_order", tts._normalize_provider_order(["cartesia", "openai", "elevenlabs"]))

    assert tts._ordered_tts_providers() == ["cartesia", "openai", "elevenlabs"]


def test_fallback_writes_actual_provider_cache(monkeypatch):
    def fail_elevenlabs(text, output_path):
        raise RuntimeError("elevenlabs unavailable")

    monkeypatch.setattr(tts, "_speak_elevenlabs", fail_elevenlabs)
    monkeypatch.setattr(tts, "_speak_cartesia", lambda text, output_path: _write_audio(output_path, b"cartesia"))

    path = asyncio.run(tts.speak_async("Hallo Lexa"))

    _, elevenlabs_path = tts._provider_cache_path("Hallo Lexa", "elevenlabs")
    _, cartesia_path = tts._provider_cache_path("Hallo Lexa", "cartesia")
    assert path == cartesia_path
    assert Path(cartesia_path).exists()
    assert not Path(elevenlabs_path).exists()


def test_failed_multi_chunk_provider_retries_whole_response(monkeypatch):
    calls: list[tuple[str, str]] = []

    def speak_elevenlabs(text, output_path):
        calls.append(("elevenlabs", text))
        if len([provider for provider, _ in calls if provider == "elevenlabs"]) == 2:
            raise RuntimeError("second chunk failed")
        return _write_audio(output_path, b"elevenlabs")

    def speak_cartesia(text, output_path):
        calls.append(("cartesia", text))
        return _write_audio(output_path, b"cartesia")

    monkeypatch.setattr(tts, "_chunk_text", lambda text: ["Erster Satz.", "Zweiter Satz."])
    monkeypatch.setattr(tts, "_speak_elevenlabs", speak_elevenlabs)
    monkeypatch.setattr(tts, "_speak_cartesia", speak_cartesia)
    monkeypatch.setattr(tts, "_concat_mp3_chunks", lambda chunks, output: _write_audio(output, b"joined"))

    path = asyncio.run(tts.speak_async("Erster Satz. Zweiter Satz."))

    assert Path(path).read_bytes() == b"joined"
    assert calls == [
        ("elevenlabs", "Erster Satz."),
        ("elevenlabs", "Zweiter Satz."),
        ("cartesia", "Erster Satz."),
        ("cartesia", "Zweiter Satz."),
    ]

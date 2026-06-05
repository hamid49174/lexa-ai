"""Regression tests for consistent TTS voice/provider selection."""

import asyncio
import os
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


def _write_cache_file(path: Path, payload: bytes = b"audio", mtime: float = 1.0) -> Path:
    path.write_bytes(payload)
    os.utime(path, (mtime, mtime))
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


def test_speak_async_strips_text_before_cache_and_provider(monkeypatch):
    calls: list[str] = []

    def speak_elevenlabs(text, output_path):
        calls.append(text)
        return _write_audio(output_path, b"elevenlabs")

    monkeypatch.setattr(tts, "_speak_elevenlabs", speak_elevenlabs)

    path = asyncio.run(tts.speak_async("  Hallo Lexa  "))

    _, expected_path = tts._provider_cache_path("Hallo Lexa", "elevenlabs")
    assert calls == ["Hallo Lexa"]
    assert path == expected_path


def test_speak_async_rejects_over_limit_text():
    with pytest.raises(ValueError, match="maximal"):
        asyncio.run(tts.speak_async("x" * (tts.MAX_TTS_TEXT_CHARS + 1)))


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


def test_prune_cache_enforces_file_count(tmp_path):
    for index in range(4):
        _write_cache_file(tmp_path / f"tts_old_{index}.mp3", mtime=float(index + 1))

    result = tts._prune_cache(max_files=2, max_age_days=0, max_mb=0)

    assert result["removed_files"] == 2
    assert sorted(path.name for path in tmp_path.glob("tts_*.mp3")) == [
        "tts_old_2.mp3",
        "tts_old_3.mp3",
    ]


def test_prune_cache_keeps_protected_file(tmp_path):
    protected = _write_cache_file(tmp_path / "tts_protected.mp3", mtime=1.0)
    _write_cache_file(tmp_path / "tts_old.mp3", mtime=2.0)
    _write_cache_file(tmp_path / "tts_new.mp3", mtime=3.0)

    result = tts._prune_cache(max_files=1, max_age_days=0, max_mb=0, protected={protected})

    assert result["removed_files"] == 2
    assert protected.exists()
    assert sorted(path.name for path in tmp_path.glob("tts_*.mp3")) == ["tts_protected.mp3"]


def test_tts_status_reports_cache_summary(tmp_path):
    _write_cache_file(tmp_path / "tts_status.mp3", payload=b"audio")

    status = tts.get_tts_status()

    assert status["cache_files"] == 1
    assert status["cache"]["files"] == 1
    assert status["cache"]["bytes"] == 5

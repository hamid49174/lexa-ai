"""Regressionstests aus dem Gesamt-Scan — Bereich D (TTS)."""
import os
import pytest
import voice.tts as tts


class _FakeResp:
    def __init__(self, chunks):
        self._chunks = chunks

    def iter_content(self, chunk_size):
        for c in self._chunks:
            yield c


def test_atomic_writer_success(tmp_path):
    out = str(tmp_path / "ok.mp3")
    res = tts._write_audio_stream_atomic(_FakeResp([b"abc", b"def"]), out, 4096)
    assert res == out
    with open(out, "rb") as f:
        assert f.read() == b"abcdef"
    assert not os.path.exists(out + ".part")


def test_atomic_writer_empty_stream_leaves_no_file(tmp_path):
    # Scan-Fix D: leerer Stream durfte keinen gueltigen (korrupten) Cache-Treffer erzeugen.
    out = str(tmp_path / "empty.mp3")
    with pytest.raises(RuntimeError):
        tts._write_audio_stream_atomic(_FakeResp([b"", b""]), out, 4096)
    assert not os.path.exists(out)
    assert not os.path.exists(out + ".part")


def test_atomic_writer_aborted_stream_leaves_no_file(tmp_path):
    out = str(tmp_path / "abort.mp3")

    class _Aborting:
        def iter_content(self, chunk_size):
            yield b"partial-data"
            raise ConnectionError("verbindung abgebrochen")

    with pytest.raises(ConnectionError):
        tts._write_audio_stream_atomic(_Aborting(), out, 4096)
    assert not os.path.exists(out)          # kein halber Cache-Treffer
    assert not os.path.exists(out + ".part")


def test_get_key_transient_error_not_cached(monkeypatch):
    # Scan-Fix D: transienter Keyring-Fehler deaktivierte den Provider bis zum Neustart.
    import keyring
    tts._keys["cartesia"] = None
    tts._keys_loaded["cartesia"] = False
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("keyring backend kurz nicht erreichbar")

    monkeypatch.setattr(keyring, "get_password", boom)
    try:
        assert tts._get_key("cartesia") is None
        assert tts._keys_loaded["cartesia"] is False   # NICHT gecacht
        assert tts._get_key("cartesia") is None
        assert calls["n"] == 2                          # beim naechsten Mal erneut versucht
    finally:
        tts._keys_loaded["cartesia"] = False
        tts._keys["cartesia"] = None

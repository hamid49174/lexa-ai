"""Regressionstests aus dem Gesamt-Scan — Bereich C (Vision)."""
import io

import pytest

import backend.vision as vision


def _png_bytes(w, h):
    if not vision._PIL_AVAILABLE:
        pytest.skip("PIL nicht verfuegbar")
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "red").save(buf, format="PNG")
    return buf.getvalue()


def test_downscale_for_groq_enforces_decompression_limit(monkeypatch):
    # Scan-Fix C: der Groq-Bytes-Pfad umging den _MAX_IMAGE_PIXELS-Deckel (untrusted Upload).
    data = _png_bytes(50, 50)  # 2500 Pixel

    monkeypatch.setattr(vision, "_MAX_IMAGE_PIXELS", 100)
    with pytest.raises(RuntimeError, match="Decompression"):
        vision._downscale_for_groq(data)

    # Unter dem Limit: normaler Pfad, liefert eine base64-Daten-URL
    monkeypatch.setattr(vision, "_MAX_IMAGE_PIXELS", 1_000_000)
    out = vision._downscale_for_groq(data)
    assert isinstance(out, str) and out.startswith("data:")

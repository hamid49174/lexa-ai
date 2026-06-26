"""Regressionstests aus dem Gesamt-Scan — Bereich D (Voice-WS-Security)."""
import backend.voice_ws as ws


def test_origin_allows_native_and_local():
    # Electron laedt per file:// -> Origin "null"/"file://"/leer.
    assert ws.ws_origin_allowed(None) is True
    assert ws.ws_origin_allowed("") is True
    assert ws.ws_origin_allowed("null") is True
    assert ws.ws_origin_allowed("file:///C:/app/index.html") is True
    assert ws.ws_origin_allowed("http://localhost:3000") is True
    assert ws.ws_origin_allowed("http://127.0.0.1:8000") is True
    assert ws.ws_origin_allowed("https://[::1]:8000") is True


def test_origin_blocks_hosted_web_origins():
    # CSWSH: ein gehostetes Web-Origin darf den Voice-Stream nicht abonnieren.
    assert ws.ws_origin_allowed("https://evil.com") is False
    assert ws.ws_origin_allowed("http://attacker.example") is False
    assert ws.ws_origin_allowed("https://lexa.example.org") is False


def test_ws_at_capacity_threshold():
    saved = dict(ws._ws_queues)
    try:
        ws._ws_queues.clear()
        assert ws.ws_at_capacity() is False
        for i in range(ws._MAX_WS_CLIENTS):
            ws._ws_queues[i] = object()
        assert ws.ws_at_capacity() is True
    finally:
        ws._ws_queues.clear()
        ws._ws_queues.update(saved)

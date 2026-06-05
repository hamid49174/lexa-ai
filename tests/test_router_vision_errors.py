from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import router_vision


def _client(monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(router_vision.router)
    monkeypatch.setattr(router_vision, "check_rate_limit", lambda *_args, **_kwargs: True)
    return TestClient(app)


def test_vision_runtime_error_redacts_client_details(monkeypatch):
    client = _client(monkeypatch)
    local_path = r"C:\Users\admin\secret.txt"

    async def fake_analyze_screenshot(**_kwargs):
        raise RuntimeError(f"failed at {local_path} token=supersecretvalue sk-testsecret12345")

    monkeypatch.setattr("backend.vision.analyze_screenshot", fake_analyze_screenshot)

    response = client.post("/vision/analyze", json={"prompt": "Beschreibe das Bild."})

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert "Bildanalyse fehlgeschlagen" in payload["error"]
    assert "[local-path-redacted]" in payload["error"]
    assert "[REDACTED]" in payload["error"]
    assert local_path not in payload["error"]
    assert "supersecretvalue" not in payload["error"]
    assert "sk-testsecret12345" not in payload["error"]


def test_vision_provider_missing_uses_product_safe_503(monkeypatch):
    client = _client(monkeypatch)

    async def fake_analyze_screenshot(**_kwargs):
        raise RuntimeError(
            "Kein Vision-Provider verfuegbar. Bitte Groq, Gemini oder OpenAI API-Key im Keyring speichern: "
            "python -c \"import keyring; keyring.set_password('lexa-ai', 'groq_api_key', 'DEIN_KEY')\""
        )

    monkeypatch.setattr("backend.vision.analyze_screenshot", fake_analyze_screenshot)

    response = client.post("/vision/analyze", json={"prompt": "Beschreibe das Bild."})

    assert response.status_code == 503
    detail = response.json()["error"]
    assert "Kein Vision-Provider fuer Bildanalyse konfiguriert" in detail
    assert "keyring.set_password" not in detail
    assert "python -c" not in detail
    assert "DEIN_KEY" not in detail


def test_vision_unexpected_error_hides_client_details(monkeypatch):
    client = _client(monkeypatch)
    local_path = r"C:\Users\admin\Desktop\private.png"

    async def fake_capture_screenshot():
        raise OSError(f"cannot read {local_path} secret=supersecretvalue")

    monkeypatch.setattr("backend.vision.capture_screenshot", fake_capture_screenshot)

    response = client.post("/vision/screenshot", json={})

    assert response.status_code == 500
    detail = response.json()["error"]
    assert detail == "Screenshot fehlgeschlagen: Details wurden lokal protokolliert."
    assert local_path not in detail
    assert "supersecretvalue" not in detail

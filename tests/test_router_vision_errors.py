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


def test_analyze_file_rejects_spoofed_image_before_provider(monkeypatch):
    client = _client(monkeypatch)

    async def fake_analyze_image(**_kwargs):
        raise AssertionError("spoofed image bytes must not reach a vision provider")

    monkeypatch.setattr("backend.vision.analyze_image", fake_analyze_image)

    response = client.post(
        "/vision/analyze-file",
        files={"file": ("spoof.png", b"not actually an image", "image/png")},
        data={"prompt": "Beschreibe das Bild."},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert "kein unterstuetztes Bild" in payload["error"]


def test_analyze_file_accepts_supported_image_signature(monkeypatch):
    client = _client(monkeypatch)
    seen = {}

    async def fake_analyze_image(*, image_input, prompt, quality_mode=False):
        seen["image_input"] = image_input
        seen["prompt"] = prompt
        seen["quality_mode"] = quality_mode
        return "Fake image analysis"

    monkeypatch.setattr("backend.vision.analyze_image", fake_analyze_image)

    response = client.post(
        "/vision/analyze-file",
        files={"file": ("screen.png", b"\x89PNG\r\n\x1a\nfake", "image/png; charset=binary")},
        data={"prompt": "Beschreibe das Bild.", "quality_mode": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["analysis"] == "Fake image analysis"
    assert seen["image_input"].startswith(b"\x89PNG")
    assert seen["prompt"] == "Beschreibe das Bild."
    assert seen["quality_mode"] is True

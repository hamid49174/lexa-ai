import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import router_chat


@pytest.fixture()
def chat_file_client(monkeypatch):
    app = FastAPI()
    app.include_router(router_chat.router)
    monkeypatch.setattr(router_chat, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_chat, "audit_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(router_chat, "conversation_history", [])
    return TestClient(app)


def _post_image(client, name="screen.png", content=b"\x89PNG\r\n\x1a\nfake"):
    return client.post(
        "/chat/file",
        files={"file": (name, content, "image/png")},
        data={"message": "Analysiere dieses Bild."},
    )


def test_image_upload_without_provider_returns_honest_fallback(chat_file_client, monkeypatch):
    monkeypatch.setattr(router_chat, "chat_file_vision_available", lambda: False)

    def fail_chat(*_args, **_kwargs):
        raise AssertionError("image uploads without vision provider must not be routed to text chat")

    monkeypatch.setattr(router_chat, "chat", fail_chat)

    response = _post_image(chat_file_client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] is None
    assert payload["requires_confirmation"] is False
    assert payload["analysis_kind"] == "image"
    assert payload["analysis_status"] == "vision_provider_required"
    assert payload["file_info"]["analysis_status"] == "vision_provider_required"
    assert "Bildanalyse ist vorbereitet" in payload["reply"]
    assert "screen.png" in payload["file_info"]["filename"]


def test_image_upload_with_provider_uses_vision_pipeline(chat_file_client, monkeypatch):
    monkeypatch.setattr(router_chat, "chat_file_vision_available", lambda: True)

    def fail_chat(*_args, **_kwargs):
        raise AssertionError("image uploads with vision provider must use the vision pipeline")

    async def fake_analyze_image(*, image_input, prompt, quality_mode=False):
        assert image_input.startswith(b"\x89PNG")
        assert "Analysiere" in prompt
        assert quality_mode is False
        return "Fake vision analysis"

    monkeypatch.setattr(router_chat, "chat", fail_chat)
    monkeypatch.setattr("backend.vision.analyze_image", fake_analyze_image)

    response = _post_image(chat_file_client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "Fake vision analysis"
    assert payload["action"] is None
    assert payload["requires_confirmation"] is False
    assert payload["analysis_status"] == "analyzed"
    assert payload["file_info"]["analysis_status"] == "analyzed"


def test_text_upload_still_uses_existing_chat_analysis(chat_file_client, monkeypatch):
    def fake_chat(prompt, history):
        assert "notes.txt" in prompt
        assert "plain file content" in prompt
        assert history == []
        return {"type": "text", "content": "Text file analysis"}

    monkeypatch.setattr(router_chat, "chat", fake_chat)

    response = chat_file_client.post(
        "/chat/file",
        files={"file": ("notes.txt", b"plain file content", "text/plain")},
        data={"message": "Bitte zusammenfassen."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "Text file analysis"
    assert payload["analysis_status"] == "text_analyzed"
    assert payload["file_info"]["analysis_status"] == "text_analyzed"

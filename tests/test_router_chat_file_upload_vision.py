import pytest
from pathlib import Path
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


def test_image_upload_uses_reported_mime_when_filename_has_no_image_suffix(chat_file_client, monkeypatch):
    monkeypatch.setattr(router_chat, "chat_file_vision_available", lambda: False)

    def fail_chat(*_args, **_kwargs):
        raise AssertionError("image uploads classified by MIME must not be routed to text chat")

    monkeypatch.setattr(router_chat, "chat", fail_chat)

    response = _post_image(chat_file_client, name="screen.bin")

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_kind"] == "image"
    assert payload["analysis_status"] == "vision_provider_required"
    assert payload["file_info"]["mime"] == "image/png"
    assert payload["file_info"]["filename"] == "screen.bin"


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


def test_spoofed_image_upload_is_rejected_before_analysis(chat_file_client, monkeypatch):
    monkeypatch.setattr(router_chat, "chat_file_vision_available", lambda: True)

    def fail_chat(*_args, **_kwargs):
        raise AssertionError("spoofed image uploads must not be routed to text chat")

    async def fail_analyze_image(**_kwargs):
        raise AssertionError("spoofed image uploads must not reach a vision provider")

    monkeypatch.setattr(router_chat, "chat", fail_chat)
    monkeypatch.setattr("backend.vision.analyze_image", fail_analyze_image)

    response = _post_image(chat_file_client, content=b"not actually an image")

    assert response.status_code == 400
    assert "kein unterstuetztes Bild" in response.json()["detail"]


def test_reported_text_mime_does_not_bypass_image_suffix_validation(chat_file_client, monkeypatch):
    def fail_chat(*_args, **_kwargs):
        raise AssertionError("image-like uploads must not be downgraded to text chat")

    monkeypatch.setattr(router_chat, "chat", fail_chat)

    response = chat_file_client.post(
        "/chat/file",
        files={"file": ("screen.png", b"not actually an image", "text/plain")},
        data={"message": "Bitte pruefen."},
    )

    assert response.status_code == 400
    assert "kein unterstuetztes Bild" in response.json()["detail"]


def test_text_upload_still_uses_existing_chat_analysis(chat_file_client, monkeypatch):
    def fake_chat(prompt, history):
        assert prompt.startswith(router_chat.FILE_ANALYSIS_DIRECTIVE)
        assert "im Hintergrund" in prompt
        assert "Nutzerfrage: Bitte zusammenfassen." in prompt
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


def test_text_upload_uses_reported_mime_when_filename_has_no_suffix(chat_file_client, monkeypatch):
    def fake_chat(prompt, history):
        assert prompt.startswith(router_chat.FILE_ANALYSIS_DIRECTIVE)
        assert "README" in prompt
        assert "plain file content" in prompt
        assert history == []
        return {"type": "text", "content": "Extensionless text analysis"}

    monkeypatch.setattr(router_chat, "chat", fake_chat)

    response = chat_file_client.post(
        "/chat/file",
        files={"file": ("README", b"plain file content", "text/plain")},
        data={"message": "Bitte zusammenfassen."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "Extensionless text analysis"
    assert payload["analysis_status"] == "text_analyzed"
    assert payload["file_info"]["mime"] == "text/plain"


def test_file_upload_audit_uses_metadata_not_filename(monkeypatch):
    entries = []
    app = FastAPI()
    app.include_router(router_chat.router)
    monkeypatch.setattr(router_chat, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_chat, "audit_log", lambda *args, **_kwargs: entries.append(args))
    monkeypatch.setattr(router_chat, "conversation_history", [])
    monkeypatch.setattr(router_chat, "chat", lambda *_args, **_kwargs: {"type": "text", "content": "ok"})

    client = TestClient(app)
    response = client.post(
        "/chat/file",
        files={"file": ("private payroll notes.txt", b"plain file content", "text/plain")},
        data={"message": "Bitte zusammenfassen."},
    )

    assert response.status_code == 200
    details = [entry[2] for entry in entries if entry[0] == "chat_file" and len(entry) >= 3]
    assert details
    for detail in details:
        assert "fileChars=" in detail
        assert "fileHash=" in detail
        assert "ext=.txt" in detail
        assert "private payroll" not in detail
        assert "FILE=" not in detail


def test_text_upload_read_error_preview_is_client_safe(monkeypatch, tmp_path):
    upload_path = tmp_path / "notes.txt"
    upload_path.write_text("placeholder", encoding="utf-8")

    def failing_read_bytes(self):
        raise OSError("failed C:\\Users\\admin\\secret.txt token=supersecretvalue")

    monkeypatch.setattr(Path, "read_bytes", failing_read_bytes)

    file_info = router_chat.extract_file_content(upload_path, "notes.txt")

    assert file_info["content"] is None
    assert "[local-path-redacted]" in file_info["preview"]
    assert "C:\\Users\\admin" not in file_info["preview"]
    assert "supersecretvalue" not in file_info["preview"]


def test_generic_upload_mime_keeps_useful_filename_metadata(tmp_path):
    upload_path = tmp_path / "notes.txt"
    upload_path.write_text("plain file content", encoding="utf-8")

    file_info = router_chat.extract_file_content(
        upload_path,
        "notes.txt",
        "application/octet-stream",
    )

    assert file_info["type"] == "text"
    assert file_info["mime"] == "text/plain"
    assert file_info["content"] == "plain file content"


def test_pdf_upload_extracts_text_with_page_metadata(tmp_path, monkeypatch):
    upload_path = tmp_path / "report.pdf"
    upload_path.write_bytes(b"%PDF fake")

    class FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakePdfReader:
        def __init__(self, path):
            assert path == str(upload_path)
            self.pages = [FakePage("Alpha summary"), FakePage("Beta risks")]

    monkeypatch.setattr(router_chat, "_load_pdf_reader_class", lambda: FakePdfReader)

    file_info = router_chat.extract_file_content(
        upload_path,
        "report.pdf",
        "application/pdf",
    )

    assert file_info["type"] == "pdf"
    assert file_info["page_count"] == 2
    assert "[Seite 1]" in file_info["content"]
    assert "Alpha summary" in file_info["content"]
    assert "Beta risks" in file_info["content"]
    assert "PDF-Text extrahiert" in file_info["preview"]


def test_pdf_upload_reader_error_preview_is_client_safe(tmp_path, monkeypatch):
    upload_path = tmp_path / "report.pdf"
    upload_path.write_bytes(b"%PDF fake")

    def fail_reader():
        raise RuntimeError("failed C:\\Users\\admin\\secret.pdf token=supersecretvalue")

    monkeypatch.setattr(router_chat, "_load_pdf_reader_class", fail_reader)

    file_info = router_chat.extract_file_content(upload_path, "report.pdf", "application/pdf")

    assert file_info["type"] == "pdf"
    assert file_info["content"] is None
    assert "[local-path-redacted]" in file_info["preview"]
    assert "C:\\Users\\admin" not in file_info["preview"]
    assert "supersecretvalue" not in file_info["preview"]


def test_pdf_upload_routes_extracted_text_to_chat(chat_file_client, monkeypatch):
    class FakePage:
        def extract_text(self):
            return "PDF body content for Lexa"

    class FakePdfReader:
        def __init__(self, _path):
            self.pages = [FakePage()]

    def fake_chat(prompt, history):
        assert prompt.startswith(router_chat.FILE_ANALYSIS_DIRECTIVE)
        assert "spaeter weiterliest" in prompt
        assert "Nutzerfrage: Bitte zusammenfassen." in prompt
        assert "report.pdf" in prompt
        assert "PDF body content for Lexa" in prompt
        assert history == []
        return {"type": "text", "content": "PDF analysis"}

    monkeypatch.setattr(router_chat, "_load_pdf_reader_class", lambda: FakePdfReader)
    monkeypatch.setattr(router_chat, "chat", fake_chat)

    response = chat_file_client.post(
        "/chat/file",
        files={"file": ("report.pdf", b"%PDF fake", "application/pdf")},
        data={"message": "Bitte zusammenfassen."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "PDF analysis"
    assert payload["analysis_status"] == "text_analyzed"
    assert payload["file_info"]["analysis_status"] == "text_analyzed"
    assert payload["file_info"]["page_count"] == 1


def test_pdf_upload_metadata_only_prompt_is_honest(chat_file_client, monkeypatch):
    def fail_reader():
        raise RuntimeError("reader unavailable")

    def fake_chat(prompt, history):
        assert prompt.startswith(router_chat.FILE_ANALYSIS_DIRECTIVE)
        assert "Inhalt nicht extrahiert" in prompt
        assert "Text konnte nicht extrahiert werden" in prompt
        assert "Bitte keine Hintergrundanalyse vortaeuschen." in prompt
        assert history == []
        return {"type": "text", "content": "Ich sehe nur Metadaten und brauche eine lesbare Datei."}

    monkeypatch.setattr(router_chat, "_load_pdf_reader_class", fail_reader)
    monkeypatch.setattr(router_chat, "chat", fake_chat)

    response = chat_file_client.post(
        "/chat/file",
        files={"file": ("report.pdf", b"%PDF fake", "application/pdf")},
        data={"message": "Bitte keine Hintergrundanalyse vortaeuschen."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "Ich sehe nur Metadaten und brauche eine lesbare Datei."
    assert payload["analysis_status"] == "metadata_only"
    assert payload["file_info"]["analysis_status"] == "metadata_only"


def test_chat_file_upload_capability_answer_is_honest(chat_file_client, monkeypatch):
    def fail_chat(*_args, **_kwargs):
        raise AssertionError("upload capability questions should not need the model")

    monkeypatch.setattr(router_chat, "chat", fail_chat)

    response = chat_file_client.post(
        "/chat",
        json={"message": "Ich lade gleich eine Datei hoch. Sag mir zuerst, welche Dateitypen du sinnvoll analysieren kannst."},
    )

    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "PDFs" in reply
    assert "Text-/Code-Dateien" in reply
    assert "Office-Dateien und Archive" in reply
    assert "nicht als Dokumentinhalt im Chat extrahiert" in reply
    assert "nicht so tun" in reply


def test_chat_stream_file_upload_capability_answer_is_honest(chat_file_client, monkeypatch):
    def fail_chat(*_args, **_kwargs):
        raise AssertionError("streamed upload capability questions should not need the model")

    monkeypatch.setattr(router_chat, "chat", fail_chat)
    monkeypatch.setattr(router_chat, "chat_stream", fail_chat)

    response = chat_file_client.post(
        "/chat/stream",
        json={"message": "Welche Upload-Dateitypen kannst du lesen und analysieren?"},
    )

    assert response.status_code == 200
    assert "Text-/Code-Dateien" in response.text
    assert "Office-Dateien und Archive" in response.text
    assert "nicht als Dokumentinhalt im Chat extrahiert" in response.text


def test_blocked_extension_is_rejected_before_chat_analysis(chat_file_client, monkeypatch):
    def fail_chat(*_args, **_kwargs):
        raise AssertionError("blocked uploads must not be routed to chat")

    monkeypatch.setattr(router_chat, "chat", fail_chat)

    response = chat_file_client.post(
        "/chat/file",
        files={"file": ("malware.exe", b"MZ", "application/octet-stream")},
        data={"message": "Bitte pruefen."},
    )

    assert response.status_code == 400
    assert "nicht erlaubt" in response.json()["detail"]


def test_path_like_filename_is_rejected(chat_file_client, monkeypatch):
    def fail_chat(*_args, **_kwargs):
        raise AssertionError("unsafe filenames must not be routed to chat")

    monkeypatch.setattr(router_chat, "chat", fail_chat)

    response = chat_file_client.post(
        "/chat/file",
        files={"file": ("../notes.txt", b"secret", "text/plain")},
        data={"message": "Bitte pruefen."},
    )

    assert response.status_code == 400
    assert "Dateiname" in response.json()["detail"]


def test_oversize_upload_cleans_temporary_file(chat_file_client, monkeypatch, tmp_path):
    monkeypatch.setattr(router_chat, "MAX_FILE_SIZE", 4)
    monkeypatch.setattr(router_chat, "MAX_FILE_SIZE_MB", 1)
    monkeypatch.setattr(router_chat.tempfile, "tempdir", str(tmp_path))

    response = chat_file_client.post(
        "/chat/file",
        files={"file": ("notes.txt", b"too large", "text/plain")},
        data={"message": "Bitte pruefen."},
    )

    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []

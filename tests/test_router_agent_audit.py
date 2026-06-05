from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import router_agent
from backend.shared import clear_pending_confirmation


def _agent_client(monkeypatch, entries):
    clear_pending_confirmation()
    app = FastAPI()
    app.include_router(router_agent.router)
    monkeypatch.setattr(router_agent, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_agent, "audit_log", lambda *args, **_kwargs: entries.append(args))
    monkeypatch.setattr(router_agent, "conversation_history", [])
    monkeypatch.setattr(router_agent, "update_history", lambda *_args, **_kwargs: None)
    return TestClient(app)


def _assert_prompt_metadata_detail(details: str):
    assert "messageChars=" in details
    assert "messageHash=" in details
    assert "MSG=" not in details
    assert "token=abc123456789" not in details
    assert "private task" not in details


def test_agent_run_audit_and_stream_error_are_client_safe(monkeypatch):
    entries = []
    client = _agent_client(monkeypatch, entries)

    async def failing_run_agent(*_args, **_kwargs):
        if False:
            yield {}
        raise RuntimeError("boom C:\\Users\\admin\\secret.txt token=supersecretvalue")

    monkeypatch.setattr("backend.agent_loop.run_agent", failing_run_agent)

    response = client.post(
        "/agent/run",
        json={"message": "private task token=abc123456789", "worker": "lexa"},
    )

    assert response.status_code == 200
    assert "[local-path-redacted]" in response.text
    assert "C:\\Users\\admin" not in response.text
    assert "supersecretvalue" not in response.text
    received = next(entry for entry in entries if entry[:2] == ("agent", "received"))
    _assert_prompt_metadata_detail(received[2])


def test_agent_chat_audit_uses_message_metadata_not_prompt(monkeypatch):
    entries = []
    client = _agent_client(monkeypatch, entries)

    async def fake_run_agent(*_args, **_kwargs):
        yield {
            "type": "done",
            "run": {"status": "completed", "summary": "Done", "worker": "lexa", "steps": []},
        }

    monkeypatch.setattr("backend.agent_loop.run_agent", fake_run_agent)

    response = client.post(
        "/agent/chat",
        json={"message": "private task token=abc123456789", "worker": "lexa"},
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Done"
    received = next(entry for entry in entries if entry[:2] == ("agent_chat", "received"))
    _assert_prompt_metadata_detail(received[2])


def test_router_agent_source_does_not_log_prompt_previews():
    source = Path(router_agent.__file__).read_text(encoding="utf-8")

    assert "MSG={sanitized[:100]}" not in source
    assert "MSG=" not in source

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def companion_confirmation_client(monkeypatch):
    import backend.router_companion as router_companion
    from backend.companion_confirmation import clear_confirmations_for_tests

    clear_confirmations_for_tests()
    audit_entries: list[tuple[str, str, str]] = []

    mock_companion = MagicMock()
    mock_companion.commands = {
        "system_info": lambda: None,
        "shutdown": lambda: None,
        "email_send": lambda: None,
    }
    mock_companion.execute.return_value = {"success": True, "data": "Executed successfully"}

    permissions = {
        "system_info": "always_allowed",
        "shutdown": "confirmation_required",
        "email_send": "confirmation_required",
    }

    monkeypatch.setattr(router_companion, "companion", mock_companion)
    monkeypatch.setattr(router_companion, "check_rate_limit", lambda *a, **kw: True)
    monkeypatch.setattr(router_companion, "is_command_allowed", lambda command: permissions.get(command, "unknown"))
    monkeypatch.setattr(router_companion, "validate_params", lambda command, params: params)
    monkeypatch.setattr(
        router_companion,
        "audit_log",
        lambda command, status, details="": audit_entries.append((command, status, details)),
    )

    app = FastAPI()
    app.include_router(router_companion.router)
    try:
        yield TestClient(app), mock_companion, audit_entries
    finally:
        clear_confirmations_for_tests()


def _prepare(client: TestClient, command: str = "shutdown", params: dict | None = None) -> dict:
    res = client.post("/companion/execute/prepare", json={"command": command, "params": params or {}})
    assert res.status_code == 200
    return res.json()


def _execute(client: TestClient, payload: dict):
    return client.post("/companion/execute", json=payload)


def test_execute_without_confirmation_id_is_rejected(companion_confirmation_client):
    client, mock_companion, _ = companion_confirmation_client

    res = _execute(client, {"command": "shutdown", "confirmed": True})

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "confirmation_required"
    mock_companion.execute.assert_not_called()


def test_execute_with_wrong_confirmation_id_is_rejected(companion_confirmation_client):
    client, mock_companion, _ = companion_confirmation_client

    res = _execute(client, {"command": "shutdown", "confirmation_id": "wrong"})

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "invalid_confirmation"
    mock_companion.execute.assert_not_called()


def test_execute_with_expired_confirmation_id_is_rejected(companion_confirmation_client, monkeypatch):
    client, mock_companion, _ = companion_confirmation_client
    import backend.companion_confirmation as companion_confirmation

    prepared = _prepare(client)
    original_time = companion_confirmation.time.time
    monkeypatch.setattr(companion_confirmation.time, "time", lambda: original_time() + 120)

    res = _execute(client, {
        "command": "shutdown",
        "confirmation_id": prepared["confirmation_id"],
        "command_hash": prepared["command_hash"],
        "action_scope": prepared["action_scope"],
    })

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "confirmation_expired"
    mock_companion.execute.assert_not_called()


def test_execute_with_wrong_command_hash_is_rejected(companion_confirmation_client):
    client, mock_companion, _ = companion_confirmation_client
    prepared = _prepare(client)

    res = _execute(client, {
        "command": "shutdown",
        "confirmation_id": prepared["confirmation_id"],
        "command_hash": "bad-hash",
        "action_scope": prepared["action_scope"],
    })

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "confirmation_hash_mismatch"
    mock_companion.execute.assert_not_called()


def test_execute_with_confirmation_id_for_changed_payload_is_rejected(companion_confirmation_client):
    client, mock_companion, _ = companion_confirmation_client
    prepared = _prepare(client, params={"delay": 1})

    res = _execute(client, {
        "command": "shutdown",
        "params": {"delay": 2},
        "confirmation_id": prepared["confirmation_id"],
        "command_hash": prepared["command_hash"],
        "action_scope": prepared["action_scope"],
    })

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "confirmation_hash_mismatch"
    mock_companion.execute.assert_not_called()


def test_execute_with_confirmation_id_for_other_action_scope_is_rejected(companion_confirmation_client):
    client, mock_companion, _ = companion_confirmation_client
    prepared = _prepare(client)

    res = _execute(client, {
        "command": "shutdown",
        "confirmation_id": prepared["confirmation_id"],
        "command_hash": prepared["command_hash"],
        "action_scope": "always_allowed",
    })

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "confirmation_scope_mismatch"
    mock_companion.execute.assert_not_called()


def test_confirmation_id_can_only_be_used_once(companion_confirmation_client):
    client, mock_companion, _ = companion_confirmation_client
    prepared = _prepare(client)
    payload = {
        "command": "shutdown",
        "confirmation_id": prepared["confirmation_id"],
        "command_hash": prepared["command_hash"],
        "action_scope": prepared["action_scope"],
    }

    first = _execute(client, payload)
    second = _execute(client, payload)

    assert first.status_code == 200
    assert first.json()["success"] is True
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "confirmation_replay"
    assert mock_companion.execute.call_count == 1


def test_prepare_then_execute_with_valid_confirmation_id_works(companion_confirmation_client):
    client, mock_companion, _ = companion_confirmation_client
    prepared = _prepare(client, params={"delay": 1})

    res = _execute(client, {
        "command": "shutdown",
        "params": {"delay": 1},
        "confirmation_id": prepared["confirmation_id"],
        "command_hash": prepared["command_hash"],
        "action_scope": prepared["action_scope"],
    })

    assert res.status_code == 200
    assert res.json()["success"] is True
    mock_companion.execute.assert_called_once_with("shutdown", {"delay": 1})


def test_confirmed_true_alone_does_not_authorize_execution(companion_confirmation_client):
    client, mock_companion, _ = companion_confirmation_client

    res = _execute(client, {"command": "shutdown", "confirmed": True})

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "confirmation_required"
    mock_companion.execute.assert_not_called()


def test_prepare_for_unknown_command_is_rejected(companion_confirmation_client):
    client, mock_companion, _ = companion_confirmation_client

    res = client.post("/companion/execute/prepare", json={"command": "mystery_cmd"})

    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "unknown_command"
    mock_companion.execute.assert_not_called()


def test_execute_unknown_command_is_rejected_even_with_confirmed_true(companion_confirmation_client):
    client, mock_companion, _ = companion_confirmation_client

    res = _execute(client, {"command": "mystery_cmd", "confirmed": True, "confirmation_id": "fake"})

    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "unknown_command"
    mock_companion.execute.assert_not_called()


def test_auditlog_redacts_tokens_and_full_sensitive_params(companion_confirmation_client):
    client, _, audit_entries = companion_confirmation_client
    params = {
        "to": "person@example.com",
        "subject": "Sensitive subject",
        "body": "private contents that must not be written fully",
    }
    prepared = _prepare(client, command="email_send", params=params)
    res = _execute(client, {
        "command": "email_send",
        "params": params,
        "confirmation_id": prepared["confirmation_id"],
        "command_hash": prepared["command_hash"],
        "action_scope": prepared["action_scope"],
    })

    assert res.status_code == 200
    audit_text = "\n".join(f"{command} {status} {details}" for command, status, details in audit_entries)
    assert "private contents that must not be written fully" not in audit_text
    assert "Sensitive subject" not in audit_text
    assert "person@example.com" not in audit_text
    assert "params=[body,subject,to]" in audit_text


def test_prepare_without_local_auth_token_is_401(monkeypatch):
    monkeypatch.setenv("LEXA_INSTANCE_TOKEN", "unit-secret")
    import backend.main as main
    import backend.router_companion as router_companion
    from backend.companion_confirmation import clear_confirmations_for_tests

    clear_confirmations_for_tests()
    mock_companion = MagicMock()
    mock_companion.commands = {"shutdown": lambda: None}
    monkeypatch.setattr(router_companion, "companion", mock_companion)
    monkeypatch.setattr(router_companion, "check_rate_limit", lambda *a, **kw: True)
    monkeypatch.setattr(router_companion, "is_command_allowed", lambda command: "confirmation_required")
    monkeypatch.setattr(router_companion, "validate_params", lambda command, params: params)

    client = TestClient(main.app)
    res = client.post("/companion/execute/prepare", json={"command": "shutdown"})

    assert res.status_code == 401


def test_execute_without_local_auth_token_is_401(monkeypatch):
    monkeypatch.setenv("LEXA_INSTANCE_TOKEN", "unit-secret")
    import backend.main as main

    client = TestClient(main.app)
    res = client.post("/companion/execute", json={"command": "shutdown", "confirmed": True})

    assert res.status_code == 401

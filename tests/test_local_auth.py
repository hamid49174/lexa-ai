from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_health_never_exposes_instance_token(monkeypatch):
    monkeypatch.setenv("LEXA_INSTANCE_TOKEN", "unit-secret")

    import backend.main as main
    import backend.shared as shared

    shared._cache.pop("health", None)
    monkeypatch.setattr(main, "get_hermes_status", lambda: {
        "health_state": "ready",
        "available": True,
        "can_run_tasks": True,
        "gateway": {"configured": True},
        "summary": "Hermes test ready.",
    })

    client = TestClient(main.app)
    res = client.get("/health")

    assert res.status_code == 200
    data = res.json()
    assert data["service"] == "lexa-ai"
    assert data["auth_required"] is True
    assert data["instance_authenticated"] is False
    assert "instance_token" not in data
    assert "unit-secret" not in json.dumps(data)


def test_health_reports_authenticated_instance_without_leaking_token(monkeypatch):
    monkeypatch.setenv("LEXA_INSTANCE_TOKEN", "unit-secret")

    import backend.main as main
    import backend.shared as shared

    shared._cache.pop("health", None)
    monkeypatch.setattr(main, "get_hermes_status", lambda: {"gateway": {}})

    client = TestClient(main.app)
    res = client.get("/health", headers={"X-Lexa-Local-Token": "unit-secret"})

    assert res.status_code == 200
    data = res.json()
    assert data["auth_required"] is True
    assert data["instance_authenticated"] is True
    assert "instance_token" not in data


def test_privileged_endpoint_requires_local_token_when_configured(monkeypatch):
    monkeypatch.setenv("LEXA_INSTANCE_TOKEN", "unit-secret")

    import backend.main as main

    client = TestClient(main.app)
    res = client.get("/i18n/language")

    assert res.status_code == 401
    assert res.json()["errorCode"] == "local_auth_required"


def test_privileged_endpoint_accepts_valid_local_token(monkeypatch):
    monkeypatch.setenv("LEXA_INSTANCE_TOKEN", "unit-secret")

    import backend.main as main

    client = TestClient(main.app)
    res = client.get("/i18n/language", headers={"X-Lexa-Local-Token": "unit-secret"})

    assert res.status_code == 200
    assert "language" in res.json()


def test_options_preflight_is_not_blocked_by_local_auth(monkeypatch):
    monkeypatch.setenv("LEXA_INSTANCE_TOKEN", "unit-secret")

    import backend.main as main

    client = TestClient(main.app)
    res = client.options(
        "/i18n/language",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert res.status_code != 401

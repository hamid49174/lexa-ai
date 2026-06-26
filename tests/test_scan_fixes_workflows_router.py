"""Regressionstests aus dem Produktivitäts-Audit — Bereich G (Workflow-Router)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.router_workflows as rw


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(rw, "check_rate_limit", lambda _b: True)
    app = FastAPI()
    app.include_router(rw.router)
    return TestClient(app, raise_server_exceptions=False)


def test_create_workflow_non_dict_body_400(client):
    # Scan-Fix G: Top-Level-Array/-String -> 400 (parse_json_body-Guard), kein 500.
    assert client.post("/workflows", json=[]).status_code == 400
    assert client.post("/workflows", json="x").status_code == 400


def test_create_workflow_wrong_types_400(client):
    # Scan-Fix G: falsch getyptes JSON -> 400 (Typ-Validierung) statt 500 in der Engine.
    for body in ({"name": 123}, {"name": "ok", "trigger": "x"},
                 {"name": "ok", "steps": 123}, {"name": "ok", "description": 5}):
        r = client.post("/workflows", json=body)
        assert r.status_code == 400, f"{body} -> {r.status_code}"


def test_update_nonexistent_workflow_404(client, monkeypatch):
    # Scan-Fix G: PUT auf nicht-existierenden Workflow -> 404 statt pauschal 400.
    class FakeEngine:
        def update_workflow(self, wid, data):
            return {"error": f"Workflow '{wid}' nicht gefunden."}
    monkeypatch.setattr(rw, "get_workflow_engine", lambda: FakeEngine())
    r = client.put("/workflows/nope", json={"name": "Neu"})
    assert r.status_code == 404


def test_enable_disable_are_rate_limited(client, monkeypatch):
    # Scan-Fix G: enable/disable hatten kein Rate-Limit (Inkonsistenz).
    calls = {"n": 0}
    monkeypatch.setattr(rw, "check_rate_limit", lambda _b: (calls.__setitem__("n", calls["n"] + 1), False)[1])

    class FakeEngine:
        def enable_workflow(self, wid):
            return {"id": wid}
        def disable_workflow(self, wid):
            return {"id": wid}
    monkeypatch.setattr(rw, "get_workflow_engine", lambda: FakeEngine())

    assert client.post("/workflows/x/enable").status_code == 429
    assert client.post("/workflows/x/disable").status_code == 429
    assert calls["n"] == 2  # beide Endpoints riefen das Rate-Limit auf

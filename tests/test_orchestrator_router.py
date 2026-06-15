"""Tests fuer Run-Store + Orchestrator-Router (Phase 48 C)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import router_orchestrator
from backend.orchestrator import store


# ── Store ────────────────────────────────────────────────────────────────
def test_store_save_get_list(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "LEXA_DATA_DIR", tmp_path)
    assert store.save_run({"run_id": "abc1", "status": "completed", "goal": "X", "mode": "fast"}) is True
    got = store.get_run("abc1")
    assert got and got["goal"] == "X" and got["updated_at"]
    listed = store.list_runs(10)
    assert any(r["run_id"] == "abc1" for r in listed)
    assert store.get_run("does-not-exist") is None


def test_store_rejects_missing_id(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "LEXA_DATA_DIR", tmp_path)
    assert store.save_run({"goal": "no id"}) is False


def test_store_sanitizes_id_and_caps_events(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "LEXA_DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "_MAX_EVENTS", 3)
    store.save_run({"run_id": "../evil id", "events": [{"i": i} for i in range(10)]})
    # Datei landet sanitisiert im runs_root, nicht ausserhalb
    files = list((tmp_path / "orchestrator_runs").glob("*.json"))
    assert len(files) == 1
    data = store.get_run("evilid")
    assert data is not None and len(data["events"]) == 3


# ── Router ───────────────────────────────────────────────────────────────
def _client(monkeypatch):
    app = FastAPI()
    app.include_router(router_orchestrator.router)
    monkeypatch.setattr(router_orchestrator, "check_rate_limit", lambda _b: True)
    monkeypatch.setattr(router_orchestrator, "ORCHESTRATOR_ENABLED", True)
    return TestClient(app)


def _sse_types(text: str) -> list[str]:
    import json
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                out.append(json.loads(line[6:]).get("type"))
            except Exception:
                pass
    return out


def test_status_endpoint(monkeypatch):
    client = _client(monkeypatch)
    resp = client.get("/orchestrator/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True and "thorough" in body["modes"]
    assert any(r["id"] == "research" for r in body["roles"])


def test_run_streams_and_persists(monkeypatch):
    saved = {}

    def fake_run(task, *, mode="thorough"):
        async def gen():
            yield {"type": "orchestrator_start", "run_id": "r1", "task": task, "mode": mode}
            yield {"type": "plan", "run_id": "r1", "plan": {"subtasks": [{"role": "research", "objective": task}]}}
            yield {"type": "done", "run_id": "r1", "run": {
                "run_id": "r1", "mode": mode, "goal": task, "answer": "ANTWORT",
                "subagent_count": 1, "agents": [], "verdicts": [], "partial": False, "elapsed_seconds": 0.1,
            }}
        return gen()

    monkeypatch.setattr(router_orchestrator, "run_orchestration", fake_run)
    monkeypatch.setattr(store, "save_run", lambda record: saved.update(record) or True)

    client = _client(monkeypatch)
    resp = client.post("/orchestrator/run", json={"task": "Vergleiche A und B", "mode": "fast"})
    assert resp.status_code == 200
    types = _sse_types(resp.text)
    assert types[0] == "orchestrator_start" and types[-1] == "done"
    # Lauf wurde persistiert
    assert saved.get("run_id") == "r1"
    assert saved.get("status") == "completed"
    assert isinstance(saved.get("events"), list) and len(saved["events"]) == 3


def test_run_blocked_when_disabled(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(router_orchestrator, "ORCHESTRATOR_ENABLED", False)
    resp = client.post("/orchestrator/run", json={"task": "x"})
    assert resp.status_code == 503


def test_runs_list_and_detail(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(store, "list_runs", lambda limit=50: [{"run_id": "r1", "status": "completed"}])
    monkeypatch.setattr(store, "get_run", lambda rid: {"run_id": rid, "answer": "A"} if rid == "r1" else None)
    assert client.get("/orchestrator/runs").json() == {"runs": [{"run_id": "r1", "status": "completed"}]}
    assert client.get("/orchestrator/runs/r1").json()["answer"] == "A"
    assert client.get("/orchestrator/runs/nope").status_code == 404

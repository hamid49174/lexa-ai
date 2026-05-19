from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch):
    import backend.router_os_agents as router_os_agents

    monkeypatch.setattr(router_os_agents, "check_rate_limit", lambda bucket: True)
    monkeypatch.setattr(router_os_agents, "audit_log", lambda *args, **kwargs: None)

    app = FastAPI()
    app.include_router(router_os_agents.router)
    return TestClient(app), router_os_agents


def test_os_agents_endpoint(monkeypatch):
    client, router_os_agents = _client(monkeypatch)
    monkeypatch.setattr(router_os_agents, "get_os_agent_registry", lambda: {
        "status": "ok",
        "agents": [{"id": "hermes"}],
    })

    res = client.get("/os/agents")

    assert res.status_code == 200
    assert res.json()["agents"][0]["id"] == "hermes"


def test_os_task_start_endpoint(monkeypatch):
    client, router_os_agents = _client(monkeypatch)

    def fake_start(title, instructions, agent, mode, timeout, timeout_seconds, create_review_draft):
        return {
            "id": "osagt_test",
            "title": title,
            "instructions": instructions,
            "agent": agent,
            "mode": mode,
            "timeout": timeout,
            "create_review_draft": create_review_draft,
            "status": "queued",
        }

    monkeypatch.setattr(router_os_agents, "start_os_agent_task", fake_start)

    res = client.post("/os/tasks", json={
        "title": "Improve Lexa OS",
        "instructions": "Route Hermes through Lexa OS runtime",
        "agent": "hermes",
        "mode": "lexa_improve",
        "timeoutSeconds": 60,
        "createReviewDraft": True,
    })

    assert res.status_code == 200
    assert res.json()["id"] == "osagt_test"
    assert res.json()["create_review_draft"] is True


def test_os_task_detail_endpoint(monkeypatch):
    client, router_os_agents = _client(monkeypatch)
    monkeypatch.setattr(router_os_agents, "get_os_agent_task", lambda task_id: {
        "id": task_id,
        "status": "completed",
    })

    res = client.get("/os/tasks/osagt_test")

    assert res.status_code == 200
    assert res.json()["status"] == "completed"

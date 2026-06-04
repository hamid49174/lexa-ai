from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(router):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_workflow_mutation_stops_when_rate_limited(monkeypatch):
    import backend.router_workflows as router_workflows

    monkeypatch.setattr(router_workflows, "check_rate_limit", lambda *_args, **_kwargs: False)
    client = _client(router_workflows.router)

    response = client.post("/workflows", json={"name": "Too fast"})

    assert response.status_code == 429


def test_vision_screenshot_stops_when_rate_limited(monkeypatch):
    import backend.router_vision as router_vision

    monkeypatch.setattr(router_vision, "check_rate_limit", lambda *_args, **_kwargs: False)
    client = _client(router_vision.router)

    response = client.post("/vision/screenshot", json={})

    assert response.status_code == 429


def test_calendar_read_stops_when_rate_limited(monkeypatch):
    import backend.router_calendar as router_calendar

    monkeypatch.setattr(router_calendar, "check_rate_limit", lambda *_args, **_kwargs: False)
    client = _client(router_calendar.router)

    response = client.get("/calendar/today")

    assert response.status_code == 429


def test_plugin_execute_stops_when_rate_limited(monkeypatch):
    import backend.router_plugins as router_plugins

    monkeypatch.setattr(router_plugins, "check_rate_limit", lambda *_args, **_kwargs: False)
    client = _client(router_plugins.router)

    response = client.post("/plugins/execute", json={"plugin": "Unit", "tool": "noop", "args": {}})

    assert response.status_code == 429

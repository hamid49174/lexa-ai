"""Tests fuer die read-only Kalender-Endpunkte /next und /search (Scan-Fix: API-Luecke)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch):
    import backend.router_calendar as router_calendar
    monkeypatch.setattr(router_calendar, "check_rate_limit", lambda *a, **k: True)
    monkeypatch.setattr(router_calendar, "audit_log", lambda *a, **k: None)
    app = FastAPI()
    app.include_router(router_calendar.router)
    return router_calendar, TestClient(app)


def test_calendar_next_returns_event(monkeypatch):
    router_calendar, client = _client(monkeypatch)
    monkeypatch.setattr(router_calendar.calendar_int, "calendar_next",
                        lambda: {"success": True, "data": {"title": "Standup"}})

    res = client.get("/calendar/next")
    assert res.status_code == 200
    assert res.json()["data"]["title"] == "Standup"


def test_calendar_search_passes_query_and_days(monkeypatch):
    router_calendar, client = _client(monkeypatch)
    seen = {}

    def fake_search(query, days):
        seen["query"] = query
        seen["days"] = days
        return {"success": True, "data": []}

    monkeypatch.setattr(router_calendar.calendar_int, "calendar_search", fake_search)

    res = client.get("/calendar/search", params={"q": "  Meeting  ", "days": 14})
    assert res.status_code == 200
    assert seen == {"query": "Meeting", "days": 14}  # getrimmt + durchgereicht


def test_calendar_search_rejects_empty_query(monkeypatch):
    router_calendar, client = _client(monkeypatch)
    res = client.get("/calendar/search", params={"q": "   "})
    assert res.status_code == 400


def test_calendar_search_bounds_days(monkeypatch):
    router_calendar, client = _client(monkeypatch)
    # days ausserhalb 1..365 -> 422 (Query-Validierung)
    assert client.get("/calendar/search", params={"q": "x", "days": 0}).status_code == 422
    assert client.get("/calendar/search", params={"q": "x", "days": 999}).status_code == 422

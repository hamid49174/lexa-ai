from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch):
    import backend.router_health as router_health

    app = FastAPI()
    app.include_router(router_health.router)
    return TestClient(app), router_health


def test_health_startup_endpoint_passes_probe_voice(monkeypatch):
    client, router_health = _client(monkeypatch)
    seen = []

    async def fake_build(*, probe_voice=False):
        seen.append(probe_voice)
        return {
            "ok": True,
            "status": "ok",
            "state": "ready",
            "summary": "Startup und Runtime-Basis sind bereit.",
            "checks": [],
        }

    monkeypatch.setattr(router_health, "build_startup_diagnostics", fake_build)

    res = client.get("/health/startup?probeVoice=true")

    assert res.status_code == 200
    assert res.json()["state"] == "ready"
    assert seen == [True]


def test_startup_diagnostics_reports_ready_when_core_runtime_is_ready(monkeypatch):
    import backend.startup_diagnostics as startup

    monkeypatch.setattr(startup, "get_ai_status", lambda: {
        "selected_provider": "openai",
        "active_provider": "openai",
        "openai": {"available": True},
        "gemini": {"available": True},
        "groq": {"available": False},
        "anthropic": {"available": False},
        "fallback_enabled": True,
        "fallback_available": ["gemini:gemini-2.5-flash"],
    })
    monkeypatch.setattr(startup, "_tool_health_summary", lambda: {
        "tools": {
            "ffmpeg": {"available": True},
            "playwright": {"available": True},
            "playwright_browser": {"available": True},
        },
        "available_count": 3,
        "total_count": 3,
        "health_pct": 100,
    })
    monkeypatch.setattr(startup, "get_hermes_status", lambda: {
        "health_state": "ready",
        "summary": "Hermes ready.",
        "obsidian_context": {"ok": True, "summary": "OS context ok."},
        "personal_os_root": "C:/OS",
    })
    monkeypatch.setattr(startup, "get_hermes_gateway_autostart_status", lambda: {"enabled": True})
    monkeypatch.setattr(startup, "get_hermes_gateway_log_summary", lambda lines: {
        "status": "ok",
        "health_state": "ok",
        "summary": "Logs ok.",
    })
    monkeypatch.setattr(startup, "_keyring_status", lambda: {"available": True, "summary": "keyring importable"})

    async def fake_voice(probe_voice=False):
        return {
            "state": "ready",
            "summary": "Voice ready.",
            "checks": [{"id": "audio-input", "state": "ok", "detail": "Microphone"}],
        }

    monkeypatch.setattr(startup, "_voice_status", fake_voice)

    import asyncio

    payload = asyncio.run(startup.build_startup_diagnostics())

    assert payload["state"] == "ready"
    assert payload["ok"] is True
    assert payload["groups"]["providers"]["fallbackAvailable"] == ["gemini:gemini-2.5-flash"]
    assert any(check["id"] == "provider-fallback" and check["state"] == "ok" for check in payload["checks"])


def test_startup_diagnostics_warns_when_selected_provider_falls_back(monkeypatch):
    import backend.startup_diagnostics as startup

    monkeypatch.setattr(startup, "get_ai_status", lambda: {
        "selected_provider": "gemini",
        "active_provider": "none",
        "openai": {"available": True},
        "gemini": {"available": False},
        "groq": {"available": False},
        "anthropic": {"available": False},
        "fallback_enabled": True,
        "fallback_available": ["openai:gpt-4o"],
    })
    monkeypatch.setattr(startup, "_tool_health_summary", lambda: {
        "tools": {
            "ffmpeg": {"available": True},
            "playwright": {"available": True},
            "playwright_browser": {"available": True},
        },
        "available_count": 3,
        "total_count": 3,
        "health_pct": 100,
    })
    monkeypatch.setattr(startup, "get_hermes_status", lambda: {
        "health_state": "ready",
        "summary": "Hermes ready.",
        "obsidian_context": {"ok": True},
        "personal_os_root": "C:/OS",
    })
    monkeypatch.setattr(startup, "get_hermes_gateway_autostart_status", lambda: {"enabled": True})
    monkeypatch.setattr(startup, "get_hermes_gateway_log_summary", lambda lines: {
        "status": "ok",
        "health_state": "ok",
        "summary": "Logs ok.",
    })
    monkeypatch.setattr(startup, "_keyring_status", lambda: {"available": True, "summary": "keyring importable"})

    async def fake_voice(probe_voice=False):
        return {
            "state": "ready",
            "summary": "Voice ready.",
            "checks": [{"id": "audio-input", "state": "ok", "detail": "Microphone"}],
        }

    monkeypatch.setattr(startup, "_voice_status", fake_voice)

    import asyncio

    payload = asyncio.run(startup.build_startup_diagnostics())

    assert payload["state"] == "attention"
    assert payload["ok"] is True
    assert payload["groups"]["providers"]["available"] == ["openai"]
    assert any(check["id"] == "providers" and check["state"] == "warn" for check in payload["checks"])
    assert any(check["id"] == "provider-fallback" and check["state"] == "ok" for check in payload["checks"])

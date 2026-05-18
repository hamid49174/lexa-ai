"""Regression tests for Lexa realtime voice architecture status."""

from voice import realtime


def test_openai_realtime_configured_but_runtime_disabled(monkeypatch):
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_ENABLED", False)
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_IMPLEMENTED", False)
    monkeypatch.setattr(
        realtime,
        "_get_secret",
        lambda secret_name, env_name: "key" if secret_name == "openai_api_key" else None,
    )
    monkeypatch.setattr(realtime, "_module_available", lambda name: name == "websockets")

    status = realtime.get_realtime_voice_status()

    assert status["configured"] is True
    assert status["provider_configured"] is True
    assert status["runtime_requested"] is False
    assert status["runtime_implemented"] is False
    assert status["runtime_active"] is False
    assert status["ready"] is False
    assert status["preferred"] == "openai_realtime"
    assert status["active_path"] == "cascaded_stt_llm_tts"
    assert "cascaded voice" in status["next_action"]
    assert status["openai"]["state"] == "configured_runtime_disabled"
    assert status["legacy"]["active"] is True


def test_openai_realtime_runtime_requested_but_not_implemented(monkeypatch):
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_ENABLED", True)
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_IMPLEMENTED", False)
    monkeypatch.setattr(
        realtime,
        "_get_secret",
        lambda secret_name, env_name: "key" if secret_name == "openai_api_key" else None,
    )
    monkeypatch.setattr(realtime, "_module_available", lambda name: name == "websockets")

    status = realtime.get_realtime_voice_status()

    assert status["runtime_requested"] is True
    assert status["runtime_implemented"] is False
    assert status["runtime_active"] is False
    assert status["ready"] is False
    assert status["active_path"] == "cascaded_stt_llm_tts"
    assert status["provider_state"] == "provider_configured_runtime_unimplemented"
    assert "Implement" in status["next_action"]
    assert status["openai"]["state"] == "configured_runtime_unimplemented"
    assert status["legacy"]["active"] is True


def test_openai_realtime_runtime_active_when_implemented(monkeypatch):
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_ENABLED", True)
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_IMPLEMENTED", True)
    monkeypatch.setattr(
        realtime,
        "_get_secret",
        lambda secret_name, env_name: "key" if secret_name == "openai_api_key" else None,
    )
    monkeypatch.setattr(realtime, "_module_available", lambda name: name == "websockets")

    status = realtime.get_realtime_voice_status()

    assert status["runtime_requested"] is True
    assert status["runtime_implemented"] is True
    assert status["runtime_active"] is True
    assert status["ready"] is True
    assert status["active_path"] == "openai_realtime"
    assert status["next_action"] == "Realtime audio runtime is active."
    assert status["openai"]["runtime_active"] is True
    assert status["legacy"]["active"] is False


def test_realtime_unconfigured_uses_cascaded_fallback(monkeypatch):
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_ENABLED", True)
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_IMPLEMENTED", True)
    monkeypatch.setattr(realtime, "_get_secret", lambda secret_name, env_name: None)
    monkeypatch.setattr(realtime, "_module_available", lambda name: False)

    status = realtime.get_realtime_voice_status()

    assert status["configured"] is False
    assert status["provider_configured"] is False
    assert status["runtime_active"] is False
    assert status["ready"] is False
    assert status["preferred"] == "cascaded_fallback"
    assert status["active_path"] == "cascaded_stt_llm_tts"
    assert status["provider_state"] == "provider_not_configured"


def test_realtime_preflight_blocks_until_transport_is_implemented(monkeypatch):
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_ENABLED", True)
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_IMPLEMENTED", False)
    monkeypatch.setattr(
        realtime,
        "_get_secret",
        lambda secret_name, env_name: "key" if secret_name == "openai_api_key" else None,
    )
    monkeypatch.setattr(realtime, "_module_available", lambda name: name == "websockets")

    preflight = realtime.get_realtime_session_preflight()

    assert preflight["ok"] is False
    assert preflight["can_start"] is False
    assert preflight["provider"] == "openai_realtime"
    assert preflight["active_path"] == "cascaded_stt_llm_tts"
    assert any("not implemented" in blocker for blocker in preflight["blockers"])
    assert preflight["warnings"]


def test_realtime_preflight_allows_active_runtime(monkeypatch):
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_ENABLED", True)
    monkeypatch.setattr(realtime, "REALTIME_RUNTIME_IMPLEMENTED", True)
    monkeypatch.setattr(
        realtime,
        "_get_secret",
        lambda secret_name, env_name: "key" if secret_name == "openai_api_key" else None,
    )
    monkeypatch.setattr(realtime, "_module_available", lambda name: name == "websockets")

    preflight = realtime.get_realtime_session_preflight()

    assert preflight["ok"] is True
    assert preflight["can_start"] is True
    assert preflight["blockers"] == []
    assert preflight["next_action"] == "Start realtime session."

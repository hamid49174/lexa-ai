"""Tests fuer das Realtime-Voice-Session-Geruest (voice/realtime_session.py).

Deckt alles ohne Live-Audio Verifizierbare ab: Protokoll-/Plan-Builder und die
Session-Zustandsmaschine (Lifecycle). Der Audio-Transport bleibt die markierte
Live-Grenze und wird hier nicht beruehrt.
"""
from voice import realtime_session as rs


def test_openai_realtime_url_uses_base_and_model():
    url = rs.openai_realtime_url()
    assert url.startswith("wss://api.openai.com/v1/realtime?model=")
    assert rs.openai_realtime_url("custom-model").endswith("model=custom-model")


def test_build_openai_session_config_shape():
    cfg = rs.build_openai_session_config(voice="verse", instructions="Hallo")
    assert cfg["type"] == "session.update"
    sess = cfg["session"]
    assert sess["voice"] == "verse"
    assert sess["instructions"] == "Hallo"
    assert sess["input_audio_format"] == "pcm16"
    assert sess["output_audio_format"] == "pcm16"
    assert sess["turn_detection"]["type"] == "server_vad"
    assert "audio" in sess["modalities"]


def test_build_gemini_live_setup_prefixes_model():
    setup = rs.build_gemini_live_setup("gemini-x")["setup"]
    assert setup["model"] == "models/gemini-x"
    assert setup["generation_config"]["response_modalities"] == ["AUDIO"]


def test_build_session_plan_per_provider():
    openai_plan = rs.build_session_plan({"preferred": "openai_realtime"})
    assert openai_plan["provider"] == "openai_realtime"
    assert openai_plan["transport"] == "websocket"
    assert openai_plan["url"].startswith("wss://")
    assert openai_plan["session_config"]["type"] == "session.update"
    assert openai_plan["audio"]["barge_in"] is True

    gemini_plan = rs.build_session_plan({"preferred": "gemini_live"})
    assert gemini_plan["provider"] == "gemini_live"
    assert "setup" in gemini_plan

    fallback = rs.build_session_plan({"preferred": "cascaded_fallback"})
    assert fallback["provider"] == "cascaded_fallback" and fallback["transport"] == "none"


def _mgr(can_start):
    preflight = {
        "can_start": can_start,
        "provider": "openai_realtime",
        "blockers": [] if can_start else ["Realtime audio transport is not implemented yet."],
        "warnings": [],
        "next_action": "ok" if can_start else "implement transport",
    }
    status = {"preferred": "openai_realtime", "active_path": "cascaded_stt_llm_tts"}
    return rs.RealtimeSessionManager(preflight_fn=lambda: preflight, status_fn=lambda: status)


def test_manager_start_blocked_when_preflight_denies():
    mgr = _mgr(can_start=False)
    res = mgr.start()
    assert res["ok"] is False and res["can_start"] is False
    assert res["session_state"] == "blocked"
    assert "not implemented" in res["blockers"][0]
    assert mgr.get() is None  # keine Session angelegt


def test_manager_start_stop_lifecycle_when_allowed():
    mgr = _mgr(can_start=True)
    res = mgr.start()
    assert res["ok"] is True and res["session_state"] == "active"
    assert res["session"]["provider"] == "openai_realtime"
    assert res["session"]["plan"]["provider"] == "openai_realtime"

    active = mgr.get()
    assert active is not None and active["id"] == res["session"]["id"]

    stopped = mgr.stop()
    assert stopped["ok"] is True and stopped["session_state"] == "stopped"
    assert stopped["was_active"] is True and stopped["active"] is False
    assert mgr.get() is None


def test_manager_plan_includes_preflight_and_plan():
    mgr = _mgr(can_start=False)
    plan = mgr.plan()
    assert "preflight" in plan and "plan" in plan
    assert plan["plan"]["provider"] == "openai_realtime"


def test_runtime_gate_stays_off_until_live_verified():
    # Ehrlichkeit: das Laufzeit-Gate ist NICHT scharf (Audio-Transport ungetestet).
    from voice import realtime
    assert realtime.REALTIME_RUNTIME_IMPLEMENTED is False

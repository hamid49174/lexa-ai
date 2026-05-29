import asyncio

from backend.shared import clear_pending_confirmation, get_pending_confirmation
from companion import hermes_desktop


def _run(coro):
    return asyncio.run(coro)


def setup_function():
    clear_pending_confirmation()


def teardown_function():
    clear_pending_confirmation()


def test_hermes_desktop_task_splits_observe_find_and_prepares_click(monkeypatch):
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", lambda **_kwargs: {
        "windows": [{"title": "Spotify", "controls": [{"name": "Play", "control_type": "Button"}]}],
        "window_count": 1,
        "control_count": 1,
    })
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", lambda text, control_type="", **_kwargs: {
        "matches": [{
            "name": "Pause",
            "control_type": control_type or "Button",
            "window_title": "Spotify",
            "rect": {"left": 100, "top": 50, "right": 180, "bottom": 90},
        }],
        "count": 1,
    })

    result = hermes_desktop.hermes_desktop_task(
        "/hermes was siehst du\n"
        "/hermes finde den Button pause im aktuellen Fenster, aendere nichts.\n"
        "klick darauf ich bestaetige es"
    )

    pending = get_pending_confirmation()
    assert result["engine"] == "lexa-hermes-desktop-controller"
    assert [step["kind"] for step in result["steps"]] == ["observe", "find", "pending_confirmation"]
    assert "Spotify" in result["summary"]
    assert pending["action"] == "hermes_desktop_commit"
    assert pending["params"]["kind"] == "click"
    assert pending["params"]["text"] == "Pause"


def test_hermes_desktop_commit_clicks_and_verifies(monkeypatch):
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_click", lambda **_kwargs: {
        "matched_text": "Pause",
        "target": "Pause",
        "x": 140,
        "y": 70,
        "window_title": "Spotify",
    })
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", lambda **_kwargs: {
        "windows": [{"title": "Spotify", "controls": [{"name": "Play", "control_type": "Button"}]}],
        "window_count": 1,
        "control_count": 1,
    })

    result = hermes_desktop.hermes_desktop_commit(kind="click", text="Pause", control_type="Button")

    assert result["kind"] == "click"
    assert "Pause" in result["summary"]
    assert result["verification"]["checked"] is True
    assert "Spotify" in result["verification"]["summary"]


def test_run_agent_routes_multi_step_hermes_desktop_prompt_to_controller(monkeypatch):
    import backend.agent_loop as agent_loop

    captured = {}

    async def fake_execute(action_name, params, **kwargs):
        captured["tool"] = action_name
        captured["params"] = params
        captured["kwargs"] = kwargs
        return {
            "success": True,
            "data": {
                "engine": "lexa-hermes-desktop-controller",
                "summary": "Controller hat beobachtet, gesucht und eine Freigabe vorbereitet.",
                "steps": [],
                "needs_confirmation": True,
            },
        }

    async def collect():
        return [
            event async for event in agent_loop.run_agent(
                "/hermes was siehst du\n/hermes finde den Button pause im aktuellen Fenster, aendere nichts.\nklick darauf ich bestaetige es",
                [],
                worker="hermes",
            )
        ]

    monkeypatch.setattr(agent_loop, "_execute_tool", fake_execute)
    monkeypatch.setattr("backend.ai_engine.chat", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM not needed")))

    events = _run(collect())

    assert captured["tool"] == "hermes_desktop_task"
    assert captured["params"]["message"].startswith("/hermes was siehst du")
    assert events[-1]["run"]["steps"][0]["action"] == "hermes_desktop_task"
    assert "Controller hat beobachtet" in events[-1]["run"]["summary"]

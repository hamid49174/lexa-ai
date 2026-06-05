import asyncio
import json
from pathlib import Path


def collect_agent_events(coro):
    async def _collect():
        return [event async for event in coro]

    return asyncio.run(_collect())


def test_agent_ledger_feature_flag_off_keeps_run_shape(monkeypatch):
    import backend.ai_engine as ai_engine
    from backend.agent_loop import run_agent

    monkeypatch.delenv("LEXA_AGENT_LEDGER", raising=False)

    def fake_chat(*args, **kwargs):
        return {"type": "text", "content": "Done"}

    monkeypatch.setattr(ai_engine, "chat", fake_chat)

    events = collect_agent_events(run_agent("hello", []))
    done = events[-1]["run"]

    assert done["summary"] == "Done"
    assert "ledger" not in done


def test_agent_ledger_feature_flag_on_emits_redacted_ledger(monkeypatch):
    import backend.ai_engine as ai_engine
    from backend.agent_loop import run_agent

    monkeypatch.setenv("LEXA_AGENT_LEDGER", "1")

    def fake_chat(*args, **kwargs):
        return {"type": "text", "content": "Done token=supersecretvalue"}

    monkeypatch.setattr(ai_engine, "chat", fake_chat)

    events = collect_agent_events(run_agent("handle request token=supersecretvalue", []))
    ledger = events[-1]["run"]["ledger"]
    ledger_json = json.dumps(ledger, sort_keys=True)

    assert ledger["status"] == "completed"
    assert ledger["plan"]["forbidden_tools"] == ["shell", "unsafe_direct_write", "mcpCallTool"]
    assert "supersecretvalue" not in ledger_json
    assert "[REDACTED]" in ledger_json


def test_agent_start_audit_uses_message_metadata_not_prompt(monkeypatch):
    import backend.ai_engine as ai_engine
    import backend.agent_loop as agent_loop

    entries = []

    def fake_chat(*args, **kwargs):
        return {"type": "text", "content": "Done"}

    monkeypatch.setattr(ai_engine, "chat", fake_chat)
    monkeypatch.setattr(agent_loop, "audit_log", lambda *args, **_kwargs: entries.append(args))

    collect_agent_events(agent_loop.run_agent("handle request token=supersecretvalue", []))

    start_entry = next(entry for entry in entries if entry[:2] == ("agent", "start"))
    details = start_entry[2]
    assert "RUN=" in details
    assert "WORKER=lexa" in details
    assert "messageChars=" in details
    assert "messageHash=" in details
    assert "handle request" not in details
    assert "supersecretvalue" not in details
    assert "MSG=" not in details


def test_agent_loop_source_does_not_log_prompt_previews():
    import backend.agent_loop as agent_loop

    source = Path(agent_loop.__file__).read_text(encoding="utf-8")

    assert "MSG={user_message[:100]}" not in source
    assert "MSG=" not in source


def test_agent_ledger_records_tool_action_and_verification(monkeypatch):
    import backend.ai_engine as ai_engine
    import backend.agent_loop as agent_loop

    monkeypatch.setenv("LEXA_AGENT_LEDGER", "1")
    calls = {"count": 0}

    def fake_chat(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "type": "tool_call",
                "content": "I will restore a backup.",
                "tool_calls": [{"name": "backup_restore", "arguments": {"backup_path": "fixture.zip"}}],
            }
        return {"type": "text", "content": "Finished"}

    async def fake_execute_tool(action_name, params):
        return {"success": True, "data": "OK token=supersecretvalue"}

    monkeypatch.setattr(ai_engine, "chat", fake_chat)
    monkeypatch.setattr(agent_loop, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(agent_loop, "is_command_allowed", lambda action_name: "confirmation_required")

    events = collect_agent_events(agent_loop.run_agent("restore backup safely", []))
    ledger = events[-1]["run"]["ledger"]
    ledger_json = json.dumps(ledger, sort_keys=True)

    assert ledger["actions"][0]["tool_name"] == "backup_restore"
    assert ledger["actions"][0]["requires_confirmation"] is True
    assert ledger["actions"][0]["risk_level"] == "critical"
    assert ledger["actions"][0]["policy"]["selected_tool"] == "backup_restore"
    assert ledger["actions"][0]["policy"]["considered_tools"] == ["backup_restore"]
    assert ledger["actions"][0]["policy"]["requires_confirmation"] is True
    assert ledger["actions"][0]["policy"]["args_hash"]
    assert ledger["actions"][0]["policy"]["arg_keys"] == ["backup_path"]
    assert ledger["verifications"][0]["passed"] is True
    assert "supersecretvalue" not in ledger_json


def test_agent_ledger_records_forced_first_hermes_tool(monkeypatch):
    import backend.ai_engine as ai_engine
    import backend.agent_loop as agent_loop

    monkeypatch.setenv("LEXA_AGENT_LEDGER", "1")

    async def fake_execute_tool(action_name, params):
        return {
            "success": True,
            "data": {
                "x": 100,
                "y": 200,
                "screen_width": 1920,
                "screen_height": 1080,
            },
        }

    def forbidden_chat(*args, **kwargs):
        raise AssertionError("desktop_position forced summary should not need LLM")

    monkeypatch.setattr(agent_loop, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(agent_loop, "is_command_allowed", lambda action_name: "allowed")
    monkeypatch.setattr(ai_engine, "chat", forbidden_chat)

    events = collect_agent_events(agent_loop.run_agent(
        "/hermes zeig mir die aktuelle Mausposition und Bildschirmgroesse, aendere nichts.",
        [],
        worker="hermes",
    ))
    ledger = events[-1]["run"]["ledger"]

    assert ledger["status"] == "completed"
    assert ledger["actions"][0]["tool_name"] == "desktop_position"
    assert ledger["actions"][0]["policy"]["selected_tool"] == "desktop_position"
    assert ledger["actions"][0]["policy"]["arg_keys"] == []
    assert ledger["verifications"][0]["action_id"] == ledger["actions"][0]["action_id"]
    assert ledger["verifications"][0]["passed"] is True
    assert events[-1]["run"]["summary"].startswith("Aktuelle Mausposition: X=100, Y=200")


def test_agent_ledger_marks_high_risk_actions_as_confirmation_required():
    from backend.agent_loop import AgentRun, _append_ledger_action, _build_agent_run_ledger

    run = AgentRun(user_message="restore backup")
    ledger = _build_agent_run_ledger(run)

    action = _append_ledger_action(
        ledger,
        action_id="step-0",
        action_name="backup_restore",
        params={"backup_path": "fixture.zip"},
        permission="allowed",
    )

    assert action.risk_level.value == "critical"
    assert action.requires_confirmation is True
    assert action.policy["selected_tool"] == "backup_restore"
    assert action.policy["policy_reason"]


def test_agent_ledger_records_rejected_tool_policy_reason():
    from backend.agent_loop import AgentRun, _append_ledger_action, _build_agent_run_ledger

    run = AgentRun(user_message="try unsafe MCP")
    ledger = _build_agent_run_ledger(run)

    action = _append_ledger_action(
        ledger,
        action_id="step-0",
        action_name="mcpCallTool",
        params={"tool": "dangerous"},
        permission="blocked",
    )

    assert action.risk_level.value == "critical"
    assert action.policy["selected_tool"] == "mcpCallTool"
    assert action.policy["rejected_tools"] == [{"tool_name": "mcpCallTool", "reason": "blocked"}]

import asyncio

from backend.agent_protocol import (
    AgentAction,
    AgentPlan,
    AgentRunLedger,
    enforce_agent_policy,
    validate_action_against_plan,
)


def collect_agent_events(coro):
    async def _collect():
        return [event async for event in coro]

    return asyncio.run(_collect())


def make_plan(**overrides):
    payload = {
        "goal": "Run a guarded tool",
        "risk_level": "medium",
        "allowed_tools": ["memory_search", "backup_restore"],
        "forbidden_tools": ["shell_exec"],
        "budget_steps": 2,
        "budget_seconds": 60,
    }
    payload.update(overrides)
    return AgentPlan(**payload)


def test_forbidden_tool_is_blocked_by_policy():
    plan = make_plan()
    action = {
        "tool_name": "shell_exec",
        "action_type": "execute",
        "scope": "agent_loop",
        "risk_level": "high",
        "requires_confirmation": True,
        "reversible": False,
    }

    decision = validate_action_against_plan(action, plan)

    assert decision.allowed is False
    assert "forbidden tool selected" in "; ".join(decision.reasons)


def test_high_action_without_confirmation_requires_review():
    plan = make_plan()
    action = {
        "tool_name": "backup_restore",
        "action_type": "execute",
        "scope": "agent_loop",
        "risk_level": "critical",
        "requires_confirmation": False,
        "reversible": False,
    }

    decision = validate_action_against_plan(action, plan)

    assert decision.allowed is False
    assert "require confirmation" in "; ".join(decision.reasons)


def test_budget_steps_exceeded_is_blocked():
    plan = make_plan(budget_steps=1)
    action = {
        "tool_name": "memory_search",
        "action_type": "read",
        "scope": "memory:metadata",
        "risk_level": "low",
        "requires_confirmation": False,
        "reversible": True,
    }

    decision = validate_action_against_plan(action, plan, step_index=1)

    assert decision.allowed is False
    assert "budget_steps exceeded" in decision.reasons


def test_missing_scope_is_rejected():
    plan = make_plan()
    action = {
        "tool_name": "memory_search",
        "action_type": "read",
        "scope": "",
        "risk_level": "low",
        "requires_confirmation": False,
        "reversible": True,
    }

    decision = validate_action_against_plan(action, plan)

    assert decision.allowed is False
    assert "tool scope must be set" in decision.reasons


def test_protected_write_without_draft_confirmation_is_rejected():
    plan = make_plan(allowed_tools=["memory_write"])
    action = {
        "tool_name": "memory_write",
        "action_type": "write",
        "scope": "core/protected",
        "risk_level": "medium",
        "requires_confirmation": False,
        "reversible": False,
    }

    decision = validate_action_against_plan(action, plan)

    assert decision.allowed is False
    assert "protected/core direct write" in "; ".join(decision.reasons)


def test_enforce_agent_policy_marks_ledger_review_required():
    plan = make_plan(allowed_tools=["memory_search"])
    action = AgentAction(
        action_id="a1",
        tool_name="memory_search",
        action_type="read",
        scope="memory:metadata",
        reason="lookup",
        reversible=True,
        requires_confirmation=False,
        risk_level="low",
    )
    ledger = AgentRunLedger(run_id="run-policy", plan=plan, actions=[action], status="running")

    decision = enforce_agent_policy(ledger)

    assert decision.allowed is True
    assert ledger.status.value == "running"

    ledger.actions.append(
        AgentAction(
            action_id="a2",
            tool_name="memory_search",
            action_type="read",
            scope="",
            reason="bad scope",
            reversible=True,
            requires_confirmation=False,
            risk_level="low",
        )
    )

    decision = enforce_agent_policy(ledger)

    assert decision.allowed is False
    assert ledger.status.value == "review_required"
    assert ledger.review is not None
    assert ledger.review.user_decision_required is True


def test_policy_feature_flag_off_does_not_change_agent_behavior(monkeypatch):
    import backend.ai_engine as ai_engine
    import backend.agent_loop as agent_loop

    monkeypatch.setenv("LEXA_AGENT_LEDGER", "1")
    monkeypatch.delenv("LEXA_AGENT_POLICY_ENFORCE", raising=False)
    calls = {"count": 0}

    def fake_chat(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"type": "tool_call", "tool_calls": [{"name": "backup_restore", "arguments": {}}]}
        return {"type": "text", "content": "done"}

    async def fake_execute_tool(action_name, params):
        return {"success": True, "data": "executed"}

    monkeypatch.setattr(ai_engine, "chat", fake_chat)
    monkeypatch.setattr(agent_loop, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(agent_loop, "is_command_allowed", lambda action_name: "allowed")

    events = collect_agent_events(agent_loop.run_agent("restore", []))

    assert any(event["type"] == "step_done" for event in events)
    assert events[-1]["run"]["ledger"]["actions"][0]["tool_name"] == "backup_restore"


def test_policy_feature_flag_on_blocks_unconfirmed_high_risk_action(monkeypatch):
    import backend.ai_engine as ai_engine
    import backend.agent_loop as agent_loop

    monkeypatch.setenv("LEXA_AGENT_LEDGER", "1")
    monkeypatch.setenv("LEXA_AGENT_POLICY_ENFORCE", "1")

    def fake_chat(*args, **kwargs):
        return {"type": "tool_call", "tool_calls": [{"name": "backup_restore", "arguments": {}}]}

    async def fail_if_called(action_name, params):
        raise AssertionError("policy should block before execution")

    monkeypatch.setattr(ai_engine, "chat", fake_chat)
    monkeypatch.setattr(agent_loop, "_execute_tool", fail_if_called)
    monkeypatch.setattr(agent_loop, "is_command_allowed", lambda action_name: "allowed")

    events = collect_agent_events(agent_loop.run_agent("restore", []))
    done = events[-1]["run"]

    assert any(event["type"] == "step_blocked" for event in events)
    assert done["ledger"]["status"] == "review_required"
    assert done["ledger"]["review"]["user_decision_required"] is True

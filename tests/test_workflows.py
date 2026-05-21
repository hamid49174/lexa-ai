import asyncio
import types

import pytest

from backend import workflows


def _run(coro):
    return asyncio.run(coro)


def test_notify_step_encodes_message_for_powershell(monkeypatch):
    captured = {}
    payload = 'hello"; Start-Process calc; $env:PATH'

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(workflows.subprocess, "run", fake_run, raising=False)

    result = _run(workflows.WorkflowEngine()._step_notify({"message": payload}, {}))

    assert result["message"] == payload
    assert captured["argv"][:2] == ["powershell", "-Command"]
    assert "FromBase64String" in captured["argv"][2]
    assert payload not in captured["argv"][2]
    assert captured["kwargs"]["timeout"] == 15


def test_workflow_tool_rejects_invalid_schema_before_execute(monkeypatch):
    calls = []
    engine = workflows.WorkflowEngine()
    engine._companion_execute = lambda tool, args: calls.append((tool, args))
    monkeypatch.setattr("backend.workflows.DB_PATH", ":memory:", raising=False)
    monkeypatch.setattr("backend.security.audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "backend.agent_reflection.reflect_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("reflection should not run")),
    )

    with pytest.raises(PermissionError, match="arguments are invalid"):
        _run(engine._step_tool(
            {"type": "tool", "tool": "app_open", "args": {"name": 123}},
            {"workflow_step_count": 1},
        ))

    assert calls == []


def test_workflow_confirmation_required_tool_is_not_auto_executed(monkeypatch):
    calls = []
    engine = workflows.WorkflowEngine()
    engine._companion_execute = lambda tool, args: calls.append((tool, args))
    monkeypatch.setattr("backend.security.audit_log", lambda *args, **kwargs: None)

    with pytest.raises(PermissionError, match="erfordert Bestaetigung"):
        _run(engine._step_tool(
            {"type": "tool", "tool": "process_kill", "args": {"pid": 123}},
            {"workflow_step_count": 1},
        ))

    assert calls == []


def test_workflow_reflection_block_prevents_tool_execution(monkeypatch):
    from backend.agent_reflection import ReflectionDecision

    calls = []
    engine = workflows.WorkflowEngine()
    engine._companion_execute = lambda tool, args: calls.append((tool, args))
    monkeypatch.setattr("backend.security.audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "backend.agent_reflection.reflect_action",
        lambda *args, **kwargs: ReflectionDecision(
            should_execute=False,
            risk_level="medium",
            confidence=0.2,
            concerns=["unit"],
            safer_alternative={"mode": "read_only"},
            requires_confirmation=False,
            verification_step="verify first",
            reason="unit_block",
        ),
    )

    with pytest.raises(PermissionError, match="safety reflection"):
        _run(engine._step_tool(
            {"type": "tool", "tool": "app_open", "args": {"name": "notepad"}},
            {"workflow_step_count": 2},
        ))

    assert calls == []


def test_workflow_tool_reflection_receives_multi_step_context(monkeypatch):
    captured = []
    calls = []
    engine = workflows.WorkflowEngine()
    engine._companion_execute = lambda tool, args: calls.append((tool, args)) or {"success": True}
    monkeypatch.setattr("backend.security.audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr("backend.security.validate_params", lambda tool, args: args)

    def fake_reflect(tool, args, **kwargs):
        captured.append((tool, args, kwargs))
        return None

    monkeypatch.setattr("backend.agent_reflection.reflect_action", fake_reflect)

    result = _run(engine._step_tool(
        {"type": "tool", "tool": "app_open", "args": {"name": "notepad"}},
        {"workflow_step_count": 3},
    ))

    assert result == {"success": True}
    assert calls == [("app_open", {"name": "notepad"})]
    assert captured == [(
        "app_open",
        {"name": "notepad"},
        {"permission": "allowed", "source": "workflow", "plan_length": 3},
    )]

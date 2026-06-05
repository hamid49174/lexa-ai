import asyncio


def _run(coro):
    return asyncio.run(coro)


class _FakeDb:
    def execute(self, *args, **kwargs):
        return self

    def commit(self):
        return None

    def close(self):
        return None


def test_scheduler_rejects_invalid_routine_action_args(monkeypatch):
    from backend import scheduler

    calls = []
    monkeypatch.setattr(scheduler, "_companion_execute", lambda command, params: calls.append((command, params)))
    monkeypatch.setattr(scheduler, "is_command_allowed", lambda command: "always_allowed")
    monkeypatch.setattr(scheduler.memory, "_get_db", lambda: _FakeDb())
    monkeypatch.setattr(scheduler, "audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        scheduler,
        "reflect_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("reflection should not run")),
    )

    _run(scheduler._run_routine({
        "name": "bad-routine",
        "actions": [{"command": "app_open", "params": {"name": 123}}],
    }))

    assert calls == []


def test_scheduler_validates_and_executes_valid_routine_action_args(monkeypatch):
    from backend import scheduler

    calls = []
    monkeypatch.setattr(scheduler, "_companion_execute", lambda command, params: calls.append((command, params)))
    monkeypatch.setattr(scheduler, "is_command_allowed", lambda command: "always_allowed")
    monkeypatch.setattr(scheduler, "validate_params", lambda command, params: params)
    monkeypatch.setattr(scheduler.memory, "_get_db", lambda: _FakeDb())
    monkeypatch.setattr(scheduler, "audit_log", lambda *args, **kwargs: None)

    _run(scheduler._run_routine({
        "name": "good-routine",
        "actions": [{"command": "app_open", "params": {"name": "notepad"}}],
    }))

    assert calls == [("app_open", {"name": "notepad"})]


def test_scheduler_write_action_triggers_reflection_before_execution(monkeypatch):
    from backend import scheduler
    from backend.agent_reflection import ReflectionDecision

    calls = []
    reflections = []
    monkeypatch.setattr(scheduler, "_companion_execute", lambda command, params: calls.append((command, params)))
    monkeypatch.setattr(scheduler, "is_command_allowed", lambda command: "allowed")
    monkeypatch.setattr(scheduler, "validate_params", lambda command, params: params)
    monkeypatch.setattr(scheduler.memory, "_get_db", lambda: _FakeDb())
    monkeypatch.setattr(scheduler, "audit_log", lambda *args, **kwargs: None)

    def fake_reflect(command, params, **kwargs):
        reflections.append((command, params, kwargs))
        return ReflectionDecision(
            should_execute=True,
            risk_level="medium",
            confidence=0.8,
            concerns=["unit"],
            requires_confirmation=False,
            verification_step="verify",
            reason="unit_pass",
        )

    monkeypatch.setattr(scheduler, "reflect_action", fake_reflect)

    _run(scheduler._run_routine({
        "name": "write-routine",
        "actions": [{"command": "clipboard_write", "params": {"text": "hello"}}],
    }))

    assert calls == [("clipboard_write", {"text": "hello"})]
    assert reflections == [(
        "clipboard_write",
        {"text": "hello"},
        {"permission": "allowed", "source": "scheduler", "plan_length": 1},
    )]


def test_scheduler_reflection_block_prevents_execution(monkeypatch):
    from backend import scheduler
    from backend.agent_reflection import ReflectionDecision

    calls = []
    monkeypatch.setattr(scheduler, "_companion_execute", lambda command, params: calls.append((command, params)))
    monkeypatch.setattr(scheduler, "is_command_allowed", lambda command: "allowed")
    monkeypatch.setattr(scheduler.memory, "_get_db", lambda: _FakeDb())
    monkeypatch.setattr(scheduler, "audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        scheduler,
        "reflect_action",
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

    _run(scheduler._run_routine({
        "name": "blocked-routine",
        "actions": [{"command": "clipboard_write", "params": {"text": "hello"}}],
    }))

    assert calls == []


def test_scheduler_reflection_audit_redacts_routine_name_and_reason(monkeypatch):
    from backend import scheduler
    from backend.agent_reflection import ReflectionDecision

    calls = []
    entries = []
    monkeypatch.setattr(scheduler, "_companion_execute", lambda command, params: calls.append((command, params)))
    monkeypatch.setattr(scheduler, "is_command_allowed", lambda command: "allowed")
    monkeypatch.setattr(scheduler.memory, "_get_db", lambda: _FakeDb())
    monkeypatch.setattr(scheduler, "audit_log", lambda *args, **kwargs: entries.append(args))
    monkeypatch.setattr(
        scheduler,
        "reflect_action",
        lambda *args, **kwargs: ReflectionDecision(
            should_execute=False,
            risk_level="medium",
            confidence=0.2,
            concerns=["unit"],
            safer_alternative={"mode": "read_only"},
            requires_confirmation=False,
            verification_step="verify first",
            reason="blocked C:\\Users\\admin\\secret.txt token=supersecretvalue",
        ),
    )

    _run(scheduler._run_routine({
        "name": "Morning C:\\Users\\admin\\secret.txt token=supersecretvalue",
        "actions": [{"command": "clipboard_write", "params": {"text": "hello"}}],
    }))

    assert calls == []
    audit_text = "\n".join(str(item[2]) for item in entries)
    entry = next(item for item in entries if item[:2] == ("scheduler", "reflection_blocked"))
    details = entry[2]
    assert "routineChars=" in details
    assert "routineHash=" in details
    assert "cmd=clipboard_write" in details
    assert "reasonChars=" in details
    assert "reasonHash=" in details
    assert "ROUTINE=" not in audit_text
    assert "REASON=" not in audit_text
    assert "C:\\Users\\admin" not in audit_text
    assert "supersecretvalue" not in audit_text


def test_scheduler_runtime_error_audit_redacts_routine_name_and_error(monkeypatch):
    from backend import scheduler

    entries = []

    def fail_execute(command, params):
        raise RuntimeError("failed C:\\Users\\admin\\secret.txt token=supersecretvalue")

    monkeypatch.setattr(scheduler, "_companion_execute", fail_execute)
    monkeypatch.setattr(scheduler, "is_command_allowed", lambda command: "allowed")
    monkeypatch.setattr(scheduler, "validate_params", lambda command, params: params)
    monkeypatch.setattr(scheduler.memory, "_get_db", lambda: _FakeDb())
    monkeypatch.setattr(scheduler, "audit_log", lambda *args, **kwargs: entries.append(args))
    monkeypatch.setattr(scheduler, "reflect_action", lambda *args, **kwargs: None)

    _run(scheduler._run_routine({
        "name": "Night C:\\Users\\admin\\secret.txt token=supersecretvalue",
        "actions": [{"command": "app_open", "params": {"name": "notepad"}}],
    }))

    audit_text = "\n".join(str(item[2]) for item in entries)
    entry = next(item for item in entries if item[:2] == ("scheduler", "error"))
    details = entry[2]
    assert "routineChars=" in details
    assert "routineHash=" in details
    assert "cmd=app_open" in details
    assert "source=scheduler" in details
    assert "errorType=RuntimeError" in details
    assert "errorChars=" in details
    assert "errorHash=" in details
    assert "ROUTINE=" not in audit_text
    assert "ERR=" not in audit_text
    assert "C:\\Users\\admin" not in audit_text
    assert "supersecretvalue" not in audit_text


def test_scheduler_confirmation_required_action_does_not_execute_side_effect(monkeypatch):
    from backend import scheduler

    calls = []
    reflections = []
    monkeypatch.setattr(scheduler, "_companion_execute", lambda command, params: calls.append((command, params)))
    monkeypatch.setattr(scheduler, "is_command_allowed", lambda command: "confirmation_required")
    monkeypatch.setattr(scheduler.memory, "_get_db", lambda: _FakeDb())
    monkeypatch.setattr(scheduler, "audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(scheduler, "reflect_action", lambda *args, **kwargs: reflections.append((args, kwargs)) or None)

    _run(scheduler._run_routine({
        "name": "dangerous-routine",
        "actions": [{"command": "process_kill", "params": {"pid": 123}}],
    }))

    assert calls == []
    assert len(reflections) == 1
    assert reflections[0][0][0] == "process_kill"


def test_scheduler_safe_plus_blocked_plan_only_executes_safe_mock(monkeypatch):
    from backend import scheduler

    calls = []
    monkeypatch.setattr(scheduler, "_companion_execute", lambda command, params: calls.append((command, params)))
    monkeypatch.setattr(
        scheduler,
        "is_command_allowed",
        lambda command: "blocked" if command == "process_kill" else "allowed",
    )
    monkeypatch.setattr(scheduler, "validate_params", lambda command, params: params)
    monkeypatch.setattr(scheduler.memory, "_get_db", lambda: _FakeDb())
    monkeypatch.setattr(scheduler, "audit_log", lambda *args, **kwargs: None)

    _run(scheduler._run_routine({
        "name": "mixed-routine",
        "actions": [
            {"command": "system_info", "params": {}},
            {"command": "process_kill", "params": {"pid": 123}},
        ],
    }))

    assert calls == [("system_info", {})]

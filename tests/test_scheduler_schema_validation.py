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

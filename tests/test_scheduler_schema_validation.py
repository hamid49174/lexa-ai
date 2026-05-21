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

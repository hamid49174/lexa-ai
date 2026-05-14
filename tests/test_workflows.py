import asyncio
import types

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


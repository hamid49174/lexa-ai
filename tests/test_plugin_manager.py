import asyncio
import types

from backend import plugin_manager as pm


def _run(coro):
    return asyncio.run(coro)


def test_yaml_shell_uses_subprocess_without_shell(monkeypatch):
    manager = pm.PluginManager()
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return types.SimpleNamespace(stdout="ok", stderr="", returncode=0)

    monkeypatch.setattr(pm.subprocess, "run", fake_run)

    result = _run(manager._yaml_action_shell({"command": "echo hello"}, {}))

    assert result["success"] is True
    assert captured["argv"] == ["echo", "hello"]
    assert "shell" not in captured["kwargs"]
    assert captured["kwargs"]["capture_output"] is True


def test_yaml_shell_supports_explicit_argv_templates(monkeypatch):
    manager = pm.PluginManager()
    captured = {}
    monkeypatch.setenv("LEXA_TEST_VALUE", "from-env")

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return types.SimpleNamespace(stdout="ok", stderr="", returncode=0)

    monkeypatch.setattr(pm.subprocess, "run", fake_run)

    result = _run(manager._yaml_action_shell({
        "argv": ["tool", "{{params.name}}", "{{env.LEXA_TEST_VALUE}}"]
    }, {"name": "from-params"}))

    assert result["success"] is True
    assert captured["argv"] == ["tool", "from-params", "from-env"]


def test_yaml_shell_blocks_shell_operator_tokens():
    manager = pm.PluginManager()

    result = _run(manager._yaml_action_shell({"command": "echo ok && whoami"}, {}))

    assert result["success"] is False
    assert "Shell-Operatoren" in result["error"]


def test_yaml_shell_blocks_operator_tokens_in_argv():
    manager = pm.PluginManager()

    result = _run(manager._yaml_action_shell({"argv": ["echo", "ok", "&&", "whoami"]}, {}))

    assert result["success"] is False
    assert "Shell-Operatoren" in result["error"]


def test_yaml_shell_blocks_dangerous_patterns():
    manager = pm.PluginManager()

    result = _run(manager._yaml_action_shell({"argv": ["cmd", "/c", "format", "C:"]}, {}))

    assert result["success"] is False
    assert "Befehl blockiert" in result["error"]

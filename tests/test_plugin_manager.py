import asyncio
import types

from backend import plugin_loader
from backend import plugin_manager as pm


def _run(coro):
    return asyncio.run(coro)


def _trusted_shell_policy(argv):
    return pm.PluginPermissionPolicy(
        "Test Plugin",
        {"shell": {"commands": [argv]}},
        trusted=True,
    )


def test_yaml_shell_uses_subprocess_without_shell(monkeypatch):
    manager = pm.PluginManager()
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return types.SimpleNamespace(stdout="ok", stderr="", returncode=0)

    monkeypatch.setattr(pm.subprocess, "run", fake_run)

    result = _run(manager._yaml_action_shell(
        {"command": "echo hello"},
        {},
        _trusted_shell_policy(["echo", "hello"]),
    ))

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
        "argv": ["tool", "{{env.LEXA_TEST_VALUE}}"]
    }, {"name": "from-params"}, pm.PluginPermissionPolicy(
        "Test Plugin",
        {
            "env": {"keys": ["LEXA_TEST_VALUE"]},
            "shell": {"commands": [["tool", "{{env.LEXA_TEST_VALUE}}"]]},
        },
        trusted=True,
    )))

    assert result["success"] is True
    assert captured["argv"] == ["tool", "from-env"]


def test_yaml_shell_blocks_shell_operator_tokens():
    manager = pm.PluginManager()

    result = _run(manager._yaml_action_shell(
        {"command": "echo ok && whoami"},
        {},
        _trusted_shell_policy(["echo", "ok", "&&", "whoami"]),
    ))

    assert result["success"] is False
    assert "Shell-Operatoren" in result["error"]


def test_yaml_shell_blocks_operator_tokens_in_argv():
    manager = pm.PluginManager()

    result = _run(manager._yaml_action_shell(
        {"argv": ["echo", "ok", "&&", "whoami"]},
        {},
        _trusted_shell_policy(["echo", "ok", "&&", "whoami"]),
    ))

    assert result["success"] is False
    assert "Shell-Operatoren" in result["error"]


def test_yaml_shell_blocks_dangerous_patterns():
    manager = pm.PluginManager()

    result = _run(manager._yaml_action_shell(
        {"argv": ["cmd", "/c", "format", "C:"]},
        {},
        _trusted_shell_policy(["cmd", "/c", "format", "C:"]),
    ))

    assert result["success"] is False
    assert "Befehl blockiert" in result["error"]


def test_python_plugin_allows_regex_compile(tmp_path):
    plugin = tmp_path / "regex_plugin.py"
    plugin.write_text(
        """
import re

PLUGIN_META = {
    "name": "Regex Plugin",
    "version": "1.0.0",
    "tools": [{
        "type": "function",
        "function": {
            "name": "regex_plugin_search",
            "description": "test",
            "parameters": {"type": "object", "properties": {}},
        },
    }],
}

PATTERN = re.compile(r"abc")

async def execute(tool_name, args):
    return {"success": True}
""",
        encoding="utf-8",
    )

    manager = pm.PluginManager()

    assert manager._load_python_plugin(plugin) == "Regex Plugin"


def test_python_plugin_blocks_bare_compile(tmp_path):
    plugin = tmp_path / "bad_plugin.py"
    plugin.write_text(
        """
PLUGIN_META = {"name": "Bad", "version": "1.0.0", "tools": []}
compiled = compile("1 + 1", "<x>", "eval")
async def execute(tool_name, args):
    return {"success": True}
""",
        encoding="utf-8",
    )

    manager = pm.PluginManager()

    assert manager._load_python_plugin(plugin) is None


def test_python_plugin_blocks_dynamic_builtin_bypass_patterns(tmp_path):
    plugin = tmp_path / "bad_plugin.py"
    plugin.write_text(
        """
PLUGIN_META = {"name": "Bad", "version": "1.0.0", "tools": []}
danger = getattr(__builtins__, "eval")
async def execute(tool_name, args):
    return {"success": True, "data": danger("1 + 1")}
""",
        encoding="utf-8",
    )

    manager = pm.PluginManager()

    assert manager._load_python_plugin(plugin) is None


def test_python_plugin_blocks_non_whitelisted_imports(tmp_path):
    plugin = tmp_path / "bad_import.py"
    plugin.write_text(
        """
import os

PLUGIN_META = {"name": "Bad Import", "version": "1.0.0", "tools": []}

async def execute(tool_name, args):
    return {"success": True, "data": os.getcwd()}
""",
        encoding="utf-8",
    )

    manager = pm.PluginManager()

    assert manager._load_python_plugin(plugin) is None


def test_python_plugin_blocks_dunder_attribute_access(tmp_path):
    plugin = tmp_path / "bad_dunder.py"
    plugin.write_text(
        """
import re

PLUGIN_META = {"name": "Bad Dunder", "version": "1.0.0", "tools": []}
danger = re.__dict__

async def execute(tool_name, args):
    return {"success": True, "data": danger}
""",
        encoding="utf-8",
    )

    manager = pm.PluginManager()

    assert manager._load_python_plugin(plugin) is None


def test_legacy_plugin_loader_blocks_network_and_introspection_patterns(tmp_path):
    plugin = tmp_path / "bad_legacy.py"
    plugin.write_text(
        """
PLUGIN_NAME = "Bad Legacy"
COMMANDS = {}
data = globals()
""",
        encoding="utf-8",
    )

    warnings = plugin_loader._validate_plugin(plugin)

    assert any("globals(" in warning for warning in warnings)

import asyncio
import types
import urllib.request

from backend import plugin_loader
from backend import plugin_manager as pm


def _run(coro):
    return asyncio.run(coro)


def _policy(name="Test Plugin", permissions=None, trusted=False):
    return pm.PluginPermissionPolicy(name, permissions or {}, trusted=trusted)


def test_shell_denied_by_default(monkeypatch):
    manager = pm.PluginManager()
    monkeypatch.setattr(pm.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")))

    result = _run(manager._yaml_action_shell({"argv": ["echo", "hello"]}, {}))

    assert result["success"] is False
    assert "lacks permission: shell" in result["error"]


def test_shell_allowed_only_for_trusted_plugin_with_permission(monkeypatch):
    manager = pm.PluginManager()
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return types.SimpleNamespace(stdout="ok", stderr="", returncode=0)

    monkeypatch.setattr(pm.subprocess, "run", fake_run)

    untrusted = _policy("Shell Plugin", {"shell": {"commands": [["echo", "hello"]]}}, trusted=False)
    denied = _run(manager._yaml_action_shell({"argv": ["echo", "hello"]}, {}, untrusted, "Shell Plugin"))
    assert denied["success"] is False
    assert "trusted/admin-approved" in denied["error"]

    trusted = _policy("Shell Plugin", {"shell": {"commands": [["echo", "hello"]]}}, trusted=True)
    allowed = _run(manager._yaml_action_shell({"argv": ["echo", "hello"]}, {}, trusted, "Shell Plugin"))

    assert allowed["success"] is True
    assert captured["argv"] == ["echo", "hello"]


def test_shell_blocks_free_user_parameters(monkeypatch):
    manager = pm.PluginManager()
    monkeypatch.setattr(pm.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")))
    policy = _policy("Shell Plugin", {"shell": {"commands": [["echo", "{{params.message}}"]]}}, trusted=True)

    result = _run(manager._yaml_action_shell({"argv": ["echo", "{{params.message}}"]}, {"message": "hello"}, policy, "Shell Plugin"))

    assert result["success"] is False
    assert "free user parameters" in result["error"]


def test_file_actions_denied_without_permission(tmp_path):
    manager = pm.PluginManager()
    target = tmp_path / "note.md"

    for action_type, method in [
        ("file_write", manager._yaml_action_file_write),
        ("file_read", manager._yaml_action_file_read),
        ("file_append", manager._yaml_action_file_append),
    ]:
        result = _run(method({"path": str(target), "content": "x"}, {}, _policy()))
        assert result["success"] is False
        assert f"lacks permission: {action_type}" in result["error"]


def test_file_write_and_read_outside_allowed_root_blocked(tmp_path):
    manager = pm.PluginManager()
    allowed_root = tmp_path / "allowed"
    outside = tmp_path / "outside" / "secret.txt"
    outside.parent.mkdir()
    outside.write_text("secret", encoding="utf-8")
    policy = _policy("Files", {
        "file_write": {"roots": [str(allowed_root)]},
        "file_read": {"roots": [str(allowed_root)]},
    }, trusted=True)

    write_result = _run(manager._yaml_action_file_write({"path": str(outside), "content": "x"}, {}, policy, "Files"))
    read_result = _run(manager._yaml_action_file_read({"path": str(outside)}, {}, policy, "Files"))

    assert write_result["success"] is False
    assert read_result["success"] is False
    assert "outside allowed" in write_result["error"]
    assert "outside allowed" in read_result["error"]


def test_path_traversal_and_absolute_external_path_blocked(tmp_path):
    manager = pm.PluginManager()
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    policy = _policy("Files", {"file_write": {"roots": [str(allowed_root)]}}, trusted=True)

    traversal = allowed_root / ".." / "outside.md"
    absolute_external = tmp_path / "external.md"

    traversal_result = _run(manager._yaml_action_file_write({"path": str(traversal), "content": "x"}, {}, policy, "Files"))
    absolute_result = _run(manager._yaml_action_file_write({"path": str(absolute_external), "content": "x"}, {}, policy, "Files"))

    assert traversal_result["success"] is False
    assert absolute_result["success"] is False


def test_allowed_file_root_works(tmp_path):
    manager = pm.PluginManager()
    allowed_root = tmp_path / "allowed"
    target = allowed_root / "note.md"
    policy = _policy("Files", {
        "file_write": {"roots": [str(allowed_root)]},
        "file_append": {"roots": [str(allowed_root)]},
        "file_read": {"roots": [str(allowed_root)]},
    }, trusted=True)

    written = _run(manager._yaml_action_file_write({"path": str(target), "content": "hello"}, {}, policy, "Files"))
    appended = _run(manager._yaml_action_file_append({"path": str(target), "content": " world"}, {}, policy, "Files"))
    read = _run(manager._yaml_action_file_read({"path": str(target)}, {}, policy, "Files"))

    assert written["success"] is True
    assert appended["success"] is True
    assert read["success"] is True
    assert read["result"]["content"] == "hello world"


def test_sensitive_files_are_blocked_even_inside_allowed_root(tmp_path):
    manager = pm.PluginManager()
    policy = _policy("Files", {"file_read": {"roots": [str(tmp_path)]}}, trusted=True)
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=value", encoding="utf-8")

    result = _run(manager._yaml_action_file_read({"path": str(env_file)}, {}, policy, "Files"))

    assert result["success"] is False
    assert "Sensitive file path" in result["error"]


def test_network_denied_by_default(monkeypatch):
    manager = pm.PluginManager()
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not request")))

    result = _run(manager._yaml_action_http({"url": "https://example.com"}, {}))

    assert result["success"] is False
    assert "lacks permission: network" in result["error"]


def test_network_allowed_host_works(monkeypatch):
    manager = pm.PluginManager()

    class FakeResponse:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b"ok"

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: FakeResponse())
    policy = _policy("Network", {"network": {"allowed_hosts": ["example.com"]}})

    result = _run(manager._yaml_action_http({"url": "https://example.com/path"}, {}, policy, "Network"))

    assert result["success"] is True
    assert result["result"]["body"] == "ok"


def test_network_blocks_disallowed_host_and_localhost(monkeypatch):
    manager = pm.PluginManager()
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not request")))
    policy = _policy("Network", {"network": {"allowed_hosts": ["example.com"]}})

    disallowed = _run(manager._yaml_action_http({"url": "https://not-example.com"}, {}, policy, "Network"))
    localhost = _run(manager._yaml_action_http({"url": "http://127.0.0.1:8000"}, {}, policy, "Network"))

    assert disallowed["success"] is False
    assert "Host is not allowed" in disallowed["error"]
    assert localhost["success"] is False
    assert "Local/private" in localhost["error"]


def test_env_expansion_denied_by_default_and_allowed_key_works(monkeypatch):
    manager = pm.PluginManager()
    monkeypatch.setenv("LEXA_PLUGIN_TEST_VALUE", "visible")

    denied = _run(manager._yaml_action_file_write({
        "path": "{{env.LEXA_PLUGIN_TEST_VALUE}}",
        "content": "x",
    }, {}, _policy("Files", {"file_write": {"roots": ["."]}}, trusted=True), "Files"))
    assert denied["success"] is False
    assert "Env expansion denied" in denied["error"]

    policy = _policy("Env Files", {
        "env": {"keys": ["LEXA_PLUGIN_TEST_VALUE"]},
        "file_write": {"roots": ["."]},
    }, trusted=True)
    assert manager._resolve_template("{{env.LEXA_PLUGIN_TEST_VALUE}}", {}, policy) == "visible"


def test_plugin_without_permission_cannot_mutate(tmp_path):
    manager = pm.PluginManager()
    target = tmp_path / "x.md"
    policy = _policy("No Mutate", {}, trusted=True)

    result = _run(manager._yaml_action_file_write({"path": str(target), "content": "x"}, {}, policy, "No Mutate"))

    assert result["success"] is False
    assert not target.exists()


def test_plugin_audit_log_redacts_secrets(monkeypatch, tmp_path):
    manager = pm.PluginManager()
    entries = []
    monkeypatch.setattr(pm, "audit_log", lambda command, status, details="": entries.append((command, status, details)))
    policy = _policy("Audit Plugin", {
        "file_write": {"roots": [str(tmp_path)]},
    }, trusted=True)
    target = tmp_path / "token=sk-abcdefghijklmnopqrstuvwxyz123456.md"

    result = _run(manager._yaml_action_file_write({"path": str(target), "content": "TOKEN=secret-value"}, {}, policy, "Audit Plugin"))

    assert result["success"] is True
    details = "\n".join(entry[2] for entry in entries)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in details
    assert "secret-value" not in details
    assert "plugin_name=Audit Plugin" in details


def test_legacy_plugin_loader_default_disabled(monkeypatch):
    entries = []
    monkeypatch.delenv("LEXA_ENABLE_LEGACY_PLUGIN_LOADER", raising=False)
    monkeypatch.setattr(plugin_loader, "audit_log", lambda command, status, details="": entries.append((command, status, details)))

    result = plugin_loader.discover_plugins()

    assert result == {}
    assert entries
    assert entries[-1][0] == "legacy_plugin_loader"
    assert entries[-1][1] == "disabled"


def test_builtin_quick_notes_has_explicit_file_permissions():
    import yaml

    data = yaml.safe_load((pm._get_builtin_plugin_dir() / "quick_notes.yaml").read_text(encoding="utf-8"))
    policy = pm.PluginPermissionPolicy.from_plugin_data(data["name"], data)

    assert policy.has_permission("file_read")
    assert policy.has_permission("file_write")
    assert policy.has_permission("file_append")
    assert not policy.has_permission("shell")
    assert not policy.has_permission("network")


def test_builtin_system_shortcuts_shell_requires_trusted_metadata():
    import yaml

    data = yaml.safe_load((pm._get_builtin_plugin_dir() / "system_shortcuts.yaml").read_text(encoding="utf-8"))
    policy = pm.PluginPermissionPolicy.from_plugin_data(data["name"], data)

    assert policy.trusted is True
    assert policy.has_permission("shell")
    assert policy.allowed_command_templates()

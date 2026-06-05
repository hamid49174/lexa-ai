import companion.engine as engine_mod


def _engine_with_commands(commands):
    engine = engine_mod.CompanionEngine.__new__(engine_mod.CompanionEngine)
    engine.commands = dict(commands)
    engine._loaded_plugins = {}
    return engine


def test_companion_execute_audit_logs_param_keys_not_values(monkeypatch):
    entries = []
    engine = _engine_with_commands({
        "unit_command": lambda name="", path="": "ok",
    })
    monkeypatch.setattr(engine_mod, "is_command_allowed", lambda _command: "allowed")
    monkeypatch.setattr(engine_mod, "audit_log", lambda *args, **_kwargs: entries.append(args))

    result = engine.execute(
        "unit_command",
        {"name": "notepad", "path": "C:\\Users\\admin\\secret.txt"},
    )

    assert result["success"] is True
    executed = next(entry for entry in entries if entry[:2] == ("unit_command", "executed"))
    details = executed[2]
    assert "paramCount=2" in details
    assert "name" in details
    assert "[sensitive]" in details
    assert "notepad" not in details
    assert "C:\\Users\\admin" not in details
    assert "params=" not in details


def test_companion_execute_audit_logs_error_metadata_not_error_text(monkeypatch):
    entries = []

    def boom():
        raise RuntimeError("failed C:\\Users\\admin\\secret.txt token=supersecretvalue")

    engine = _engine_with_commands({"unit_boom": boom})
    monkeypatch.setattr(engine_mod, "is_command_allowed", lambda _command: "allowed")
    monkeypatch.setattr(engine_mod, "audit_log", lambda *args, **_kwargs: entries.append(args))

    result = engine.execute("unit_boom", {})

    assert result["success"] is False
    error_entry = next(entry for entry in entries if entry[:2] == ("unit_boom", "error"))
    details = error_entry[2]
    assert "errorType=RuntimeError" in details
    assert "errorChars=" in details
    assert "errorHash=" in details
    assert "C:\\Users\\admin" not in details
    assert "supersecretvalue" not in details
    assert "error=" not in details

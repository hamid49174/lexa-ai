import pytest

from backend.tool_registry import validate_tool_arguments
from companion import dev_tools, engine as engine_mod, file_tools, media, system_tools


def _engine_for(command, func, monkeypatch):
    engine = engine_mod.CompanionEngine.__new__(engine_mod.CompanionEngine)
    engine.commands = {command: func}
    monkeypatch.setattr(engine_mod, "audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(engine_mod, "is_command_allowed", lambda _command: "always_allowed")
    return engine


@pytest.mark.parametrize(
    ("command", "func", "params"),
    [
        ("archive_create", file_tools.archive_create, {"path": "missing.txt"}),
        ("archive_extract", file_tools.archive_extract, {"path": "missing.zip", "dest": "out"}),
        ("archive_list", file_tools.archive_list, {"path": "missing.zip"}),
        ("backup_create", file_tools.backup_create, {"source": "missing", "dest": "out"}),
        ("convert_media", media.convert_media, {"path": "missing.mp4", "format": "mp3"}),
        ("dns_lookup", system_tools.dns_lookup, {"domain": "bad host!"}),
        ("docker_logs", dev_tools.docker_logs, {"name": "bad host!"}),
        ("docker_start", dev_tools.docker_start, {"name": "bad host!"}),
        ("docker_stop", dev_tools.docker_stop, {"name": "bad host!"}),
        ("git_add", dev_tools.git_add, {"path": "missing-repo", "files": "README.md"}),
        ("git_branch_list", dev_tools.git_branch_list, {"path": "missing-repo"}),
        ("git_commit", dev_tools.git_commit, {"path": "missing-repo", "message": "test"}),
        ("git_diff", dev_tools.git_diff, {"path": "missing-repo"}),
        ("git_log", dev_tools.git_log, {"path": "missing-repo"}),
        ("git_pull", dev_tools.git_pull, {"path": "missing-repo"}),
        ("git_push", dev_tools.git_push, {"path": "missing-repo"}),
        ("git_status", dev_tools.git_status, {"path": "missing-repo"}),
        ("image_convert", file_tools.image_convert, {"path": "missing.png", "format": "jpg"}),
        ("image_info", file_tools.image_info, {"path": "missing.png"}),
        ("image_resize", file_tools.image_resize, {"path": "missing.png", "width": 100}),
    ],
)
def test_execute_accepts_registry_param_aliases(command, func, params, monkeypatch):
    engine = _engine_for(command, func, monkeypatch)
    schema_params = validate_tool_arguments(command, params)

    result = engine.execute(command, schema_params)

    assert "unexpected keyword argument" not in str(result)
    assert "Falsche Parameter" not in str(result)


def test_execute_accepts_organize_downloads_registry_path(tmp_path, monkeypatch):
    engine = _engine_for("organize_downloads", file_tools.organize_downloads, monkeypatch)
    schema_params = validate_tool_arguments("organize_downloads", {"path": str(tmp_path)})

    result = engine.execute("organize_downloads", schema_params)

    assert result["success"] is True
    assert result["data"] == {"moved_files": 0, "categories": {}}


def test_execute_maps_batch_rename_replacement_schema(tmp_path, monkeypatch):
    target = tmp_path / "old.txt"
    target.write_text("content", encoding="utf-8")
    engine = _engine_for("batch_rename", file_tools.batch_rename, monkeypatch)
    schema_params = validate_tool_arguments(
        "batch_rename",
        {"folder": str(tmp_path), "pattern": "old", "replacement": "new"},
    )

    result = engine.execute("batch_rename", schema_params)

    assert result["success"] is True
    assert result["data"] == [{"old": "old.txt", "new": "new.txt"}]
    assert (tmp_path / "new.txt").exists()
    assert not target.exists()


def test_execute_drops_legacy_optional_params_without_dispatch_error(tmp_path, monkeypatch):
    monkeypatch.setattr(file_tools, "BACKUP_CONFIG_PATH", tmp_path / "backup_config.json")
    engine = _engine_for("backup_list", file_tools.backup_list, monkeypatch)
    schema_params = validate_tool_arguments("backup_list", {"dest": str(tmp_path)})

    result = engine.execute("backup_list", schema_params)

    assert result == {"success": True, "data": []}


def test_execute_drops_image_batch_height_without_dispatch_error(monkeypatch):
    engine = _engine_for("image_batch_resize", file_tools.image_batch_resize, monkeypatch)
    schema_params = validate_tool_arguments(
        "image_batch_resize",
        {"folder": "missing", "width": 320, "height": 240},
    )

    result = engine.execute("image_batch_resize", schema_params)

    assert "unexpected keyword argument" not in str(result)
    assert "Falsche Parameter" not in str(result)


def test_execute_drops_time_tracking_task_without_starting_tracker(monkeypatch):
    def fake_start():
        return "started"

    engine = _engine_for("time_tracking_start", fake_start, monkeypatch)
    schema_params = validate_tool_arguments("time_tracking_start", {"task": "Focus"})

    result = engine.execute("time_tracking_start", schema_params)

    assert result == {"success": True, "data": "started"}


def test_normalize_command_params_keeps_explicit_canonical_value():
    normalized = engine_mod._normalize_command_params(
        "archive_create",
        {"path": "schema-value", "source": "canonical-value"},
    )

    assert normalized == {"source": "canonical-value"}

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_config_resolves_packaged_data_dir_outside_bundle():
    src = read("backend/config.py")

    assert "def resolve_data_dir" in src
    assert 'os.environ.get("LEXA_DATA_DIR")' in src
    assert 'getattr(sys, "frozen", False)' in src
    assert 'Path(base) / "lexa-ai"' in src
    assert "LEXA_DATA_DIR_SOURCE" in src
    assert '"packaged_default"' in src
    assert '"user_data_default"' in src
    assert '"project_root"' not in src
    assert "data_dir.mkdir(parents=True, exist_ok=True)" in src
    assert "LEXA_DATA_DIR, LEXA_DATA_DIR_SOURCE = _resolve_data_dir_with_source()" in src


def test_pyinstaller_entry_sets_data_dir_before_backend_imports():
    src = read("backend/pyinstaller_entry.py")

    assert "def _default_data_dir" in src
    assert 'if not os.environ.get("LEXA_DATA_DIR")' in src
    assert 'os.environ["LEXA_DATA_DIR"] = str(data_dir)' in src
    assert src.index('os.environ["LEXA_DATA_DIR"] = str(data_dir)') < src.index("import uvicorn")


def test_runtime_db_and_audit_modules_use_central_data_dir():
    for module in [
        "backend/memory.py",
        "backend/productivity.py",
        "backend/reminders.py",
        "backend/smart_memory.py",
        "backend/workflows.py",
        "backend/security.py",
        "backend/mcp_registry.py",
        "backend/router_stripe.py",
        "backend/main.py",
    ]:
        src = read(module)
        assert "LEXA_DATA_DIR" in src, module
        assert 'os.environ.get("LEXA_DATA_DIR", str(Path(__file__).resolve().parent.parent))' not in src, module
        assert 'os.environ.get("LEXA_DATA_DIR", str(PROJECT_ROOT))' not in src, module


def test_plugin_dirs_use_central_data_dir_for_packaged_builds():
    loader_src = read("backend/plugin_loader.py")
    manager_src = read("backend/plugin_manager.py")

    assert "LEXA_DATA_DIR_SOURCE" in loader_src
    assert 'LEXA_DATA_DIR_SOURCE in {"env", "packaged_default", "user_data_default"}' in loader_src
    assert "PLUGINS_DIR = LEXA_DATA_DIR / \"plugins\"" in loader_src
    assert 'os.environ.get("LEXA_DATA_DIR"' not in loader_src

    assert "LEXA_DATA_DIR_SOURCE" in manager_src
    assert 'LEXA_DATA_DIR_SOURCE in {"env", "packaged_default", "user_data_default"}' in manager_src
    assert 'return LEXA_DATA_DIR / "plugins"' in manager_src


def test_companion_runtime_artifacts_use_central_data_dir():
    for module in [
        "companion/app_discovery.py",
        "companion/browser.py",
        "companion/calendar_integration.py",
        "companion/communication.py",
        "companion/engine.py",
        "companion/file_tools.py",
        "companion/media.py",
    ]:
        src = read(module)
        assert "LEXA_DATA_DIR" in src, module
        assert 'os.environ.get("LEXA_DATA_DIR"' not in src, module
        assert 'Path(__file__).resolve().parent.parent' not in src, module
        assert 'Path(__file__).parent.parent' not in src, module

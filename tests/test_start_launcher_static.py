from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_start_bat_does_not_kill_all_electron_processes():
    src = (REPO_ROOT / "start.bat").read_text(encoding="utf-8").lower()

    assert "taskkill /f /im electron.exe" not in src
    assert "get-ciminstance win32_process" in src
    assert "$_.name -eq 'electron.exe'" in src
    assert "$_.executablepath -eq $resolved" in src


def test_start_bat_keeps_electron_cleanup_lexa_scoped():
    src = (REPO_ROOT / "start.bat").read_text(encoding="utf-8")

    assert ":STOP_LEXA_ELECTRON" in src
    assert "frontend\\node_modules\\electron\\dist\\electron.exe" in src
    assert "Stop-Process -Id $_.ProcessId" in src


def test_start_bat_invokes_pip_through_venv_python():
    src = (REPO_ROOT / "start.bat").read_text(encoding="utf-8").lower()

    assert "venv\\scripts\\python.exe -m pip show fastapi" in src
    assert "venv\\scripts\\python.exe -m pip install -r requirements.txt --quiet" in src
    assert "venv\\scripts\\pip " not in src
    assert "venv\\scripts\\pip.exe" not in src


def test_start_bat_sets_personal_os_root_for_backend_children():
    src = (REPO_ROOT / "start.bat").read_text(encoding="utf-8")

    assert "PERSONAL_OS_ROOT" in src
    assert "PERSONAL_OS_SDK_ROOT" in src
    assert "OneDrive - Office\\Desktop\\OS\\11_Integrations\\MCP\\os-mcp-server\\dist\\index.js" in src

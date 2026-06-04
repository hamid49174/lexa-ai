from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_backend_guards_recursive_clean_target():
    src = (REPO_ROOT / "build_backend.py").read_text(encoding="utf-8")

    assert "_assert_build_dist_path_safe" in src
    assert 'resolved.name != "backend-dist"' in src
    assert "resolved.parent != root" in src
    assert src.index("_assert_build_dist_path_safe(path)") < src.index("shutil.rmtree(path")


def test_build_backend_clean_handles_readonly_onedrive_locks():
    src = (REPO_ROOT / "build_backend.py").read_text(encoding="utf-8")

    assert "def _make_writable_and_retry" in src
    assert "os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)" in src
    assert "shutil.rmtree(path, onexc=_make_writable_and_retry)" in src
    assert "shutil.rmtree(path, onerror=_make_writable_and_retry)" in src
    assert "pause OneDrive sync" in src
    assert "print(f\"[Build] ERROR: {exc}\")" in src


def test_build_backend_keeps_generated_spec_out_of_repo_root():
    src = (REPO_ROOT / "build_backend.py").read_text(encoding="utf-8")

    assert 'BUILD = ROOT / "build"' in src
    assert "BUILD.mkdir(exist_ok=True)" in src
    assert '"--specpath", str(BUILD)' in src


def test_build_backend_removes_runtime_artifacts_from_bundle():
    src = (REPO_ROOT / "build_backend.py").read_text(encoding="utf-8")

    assert "FORBIDDEN_BACKEND_RUNTIME_ARTIFACTS" in src
    assert '"audit.log"' in src
    assert '"bridge-audit.log"' in src
    assert '"lexa_memory.db-wal"' in src
    assert "def remove_forbidden_backend_runtime_artifacts" in src
    assert "candidate.unlink()" in src
    assert "remove_forbidden_backend_runtime_artifacts()" in src


def test_checked_in_pyinstaller_spec_is_portable():
    src = (REPO_ROOT / "lexa-backend.spec").read_text(encoding="utf-8")

    assert "ROOT = Path(__file__).resolve().parent" in src
    assert "OneDrive" not in src
    assert "Desktop" not in src
    assert "str(ROOT / 'backend' / 'pyinstaller_entry.py')" in src
    assert "str(ROOT / 'command_whitelist.json')" in src

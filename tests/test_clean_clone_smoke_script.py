import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_clean_clone_smoke.ps1"


def test_clean_clone_smoke_script_is_non_destructive():
    src = SCRIPT.read_text(encoding="utf-8")

    assert "Remove-Item" not in src
    assert "git add" not in src.lower()
    assert "personal_os" in src
    assert "lexa_memory.db" in src
    assert "evals/results" in src
    assert "Resolve-PythonForVenv" in src
    assert "KeepTemp" in src
    assert "NoInstall" in src
    assert "package-lock.json" in src
    assert "StartsWith(\"./\")" in src
    assert "clean-copy quick gate failed with exit code" in src


def test_clean_clone_smoke_dry_run_passes():
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-DryRun",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout
    assert "Dry-run passed" in result.stdout


def test_clean_clone_smoke_blocks_existing_target(tmp_path):
    target = tmp_path / "existing-clean-copy"
    target.mkdir()

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-CloneRoot",
            str(target),
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )

    assert result.returncode != 0
    assert "CloneRoot already exists" in result.stdout


def test_clean_clone_noinstall_blocks_quick_gate_combination():
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-DryRun",
            "-NoInstall",
            "-RunQuickGate",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )

    assert result.returncode != 0
    assert "cannot be combined with -NoInstall" in result.stdout


def test_clean_clone_dry_run_supports_source_only_workspace(tmp_path):
    (tmp_path / "requirements.txt").write_text("", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-RepoRoot",
            str(tmp_path),
            "-DryRun",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout
    assert "source-only file scan" in result.stdout


def test_clean_clone_preserves_dotfile_paths(tmp_path):
    target = tmp_path / "clean-copy"

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-CloneRoot",
            str(target),
            "-NoInstall",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout
    assert (target / ".gitignore").exists()
    assert (target / ".github" / "workflows" / "quality-gates.yml").exists()

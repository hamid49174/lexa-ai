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
    assert "credentials|secrets" in src
    assert "service[-_]?account" in src
    assert "pfx|p12|pem|ppk|key|pvk|cer|crt|spc|jks|keystore" in src
    assert "\\.env($|\\.|/)" in src
    assert "\\.env\\.example" in src
    assert "Resolve-PythonForVenv" in src
    assert "KeepTemp" in src
    assert "NoInstall" in src
    assert "package-lock.json" in src
    assert "npm-shrinkwrap.json" in src
    assert "yarn.lock" in src
    assert "pnpm-lock.yaml" in src
    assert "$frontendNpmCiLockfiles" in src
    assert "$frontendAlternativeLockfiles" in src
    assert "if ($DryRun -or -not $Install)" in src
    assert "Write-FrontendLockfileDriftWarningsFromSourceList $files" in src
    assert "frontend clean clone source list mixes npm ci and non-npm lockfile(s)" in src
    assert "frontend clean clone source list uses non-npm lockfile(s)" in src
    assert "frontend clean clone source list has frontend/package.json without package-lock.json or npm-shrinkwrap.json" in src
    assert "frontend npm ci lockfile" in src
    assert "multiple frontend npm ci lockfiles found" in src
    assert "frontend npm ci will ignore non-npm lockfile(s)" in src
    assert "clean smoke does not run yarn/pnpm install" in src
    assert "without package-lock.json or npm-shrinkwrap.json" in src
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


def test_clean_clone_dry_run_warns_for_mixed_frontend_lockfiles(tmp_path):
    (tmp_path / "requirements.txt").write_text("", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "frontend" / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

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
    assert "frontend clean clone source list mixes npm ci and non-npm lockfile(s)" in result.stdout
    assert "pnpm-lock.yaml" in result.stdout


def test_clean_clone_dry_run_warns_for_non_npm_frontend_lockfile_only(tmp_path):
    (tmp_path / "requirements.txt").write_text("", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "frontend" / "yarn.lock").write_text("# yarn lockfile\n", encoding="utf-8")

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
    assert "frontend clean clone source list uses non-npm lockfile(s)" in result.stdout
    assert "clean smoke does not run" in result.stdout
    assert "yarn/pnpm install" in result.stdout
    assert "yarn.lock" in result.stdout


def test_clean_clone_noinstall_warns_for_non_npm_frontend_lockfile_only(tmp_path):
    repo_root = tmp_path / "repo"
    target = tmp_path / "clean-copy"
    (repo_root / "frontend").mkdir(parents=True)
    (repo_root / "scripts").mkdir()
    (repo_root / "requirements.txt").write_text("", encoding="utf-8")
    (repo_root / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (repo_root / "frontend" / "yarn.lock").write_text("# yarn lockfile\n", encoding="utf-8")
    for name in [
        "run_quality_gates.ps1",
        "run_eval_regression_gate.ps1",
        "run_release_candidate_check.ps1",
    ]:
        (repo_root / "scripts" / name).write_text("Write-Host ok\n", encoding="utf-8")

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-RepoRoot",
            str(repo_root),
            "-CloneRoot",
            str(target),
            "-NoInstall",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout
    assert "frontend clean clone source list uses non-npm lockfile(s)" in result.stdout
    assert "yarn.lock" in result.stdout
    assert (target / "frontend" / "yarn.lock").exists()


def test_clean_clone_source_only_blocks_generic_credentials(tmp_path):
    (tmp_path / "requirements.txt").write_text("", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "credentials.yaml").write_text("token: placeholder\n", encoding="utf-8")

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

    assert result.returncode != 0
    assert "Source-only workspace contains risky paths" in result.stdout
    assert "config/credentials.yaml" in result.stdout


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

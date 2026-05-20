import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_risky_artifacts.ps1"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )


def test_normal_source_file_passes_from_staged_list(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text("backend/main.py\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 0, result.stdout
    assert "Risky artifact check passed" in result.stdout


def test_risky_staged_file_fails(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text("personal_os/private.md\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Risky staged path" in result.stdout


def test_secret_scan_path_fails_without_deleting_file(tmp_path):
    secret_file = tmp_path / "candidate.env"
    secret_file.write_text("api_key=sk_test_1234567890abcdef\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert secret_file.exists()
    assert "Secret-like pattern" in result.stdout


def test_artifact_path_blocks_user_data(tmp_path):
    artifact = tmp_path / "dist"
    artifact.mkdir()
    (artifact / "lexa_memory.db").write_text("not real sqlite", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-ArtifactPath", str(artifact))

    assert result.returncode == 1
    assert "Forbidden file" in result.stdout or "Risky" in result.stdout


def test_signing_keys_are_blocked_from_staging(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text("release/windows_signing.pfx\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Risky staged path" in result.stdout


def test_certificate_files_are_blocked_from_staging(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text("release/signing/public-cert.cer\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Risky staged path" in result.stdout


def test_keystore_files_are_blocked_from_staging(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text("release/signing/windows.keystore\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Risky staged path" in result.stdout


def test_signing_password_patterns_are_blocked(tmp_path):
    secret_file = tmp_path / "signing.txt"
    secret_file.write_text("CSC_KEY_PASSWORD=supersecretvalue", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_signtool_password_command_patterns_are_blocked(tmp_path):
    secret_file = tmp_path / "signtool.txt"
    secret_file.write_text("signtool sign /f cert.pfx /p supersecretvalue app.exe", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_dot_env_is_blocked_from_staging(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text(".env\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Risky staged path" in result.stdout

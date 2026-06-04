import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_website_smoke.ps1"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )


def test_website_smoke_scans_package_metadata_files_only():
    src = SCRIPT.read_text(encoding="utf-8")

    assert "$packageSecretScanPaths = @(" in src
    assert "Test-Path -LiteralPath $_ -PathType Leaf" in src


def test_website_smoke_blocks_generic_credential_files(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "credentials.yaml").write_text("token: placeholder\n", encoding="utf-8")

    result = run_script("-WebsiteRoot", str(tmp_path))

    assert result.returncode != 0
    assert "Potential website secret files found" in result.stdout
    assert "config/credentials.yaml" in result.stdout


def test_website_smoke_uses_central_secret_scan_for_static_assets(tmp_path):
    (tmp_path / "config.js").write_text(
        'window.LEXA_CONFIG = { serviceRoleKey: "supersecretvalue" };\n',
        encoding="utf-8",
    )

    result = run_script("-WebsiteRoot", str(tmp_path))

    assert result.returncode != 0
    assert "Potential website secret patterns found by central risky-artifact scanner" in result.stdout
    assert "Secret-like pattern" in result.stdout


def test_website_smoke_uses_central_secret_scan_for_lockfile(tmp_path):
    (tmp_path / "package-lock.json").write_text(
        '{"packages":{"node_modules/private":{"resolved":"https://user:supersecretvalue@registry.example/private.tgz"}}}\n',
        encoding="utf-8",
    )

    result = run_script("-WebsiteRoot", str(tmp_path))

    assert result.returncode != 0
    assert "Potential website secret patterns found by central risky-artifact scanner" in result.stdout
    assert "package-lock.json" in result.stdout


def test_website_smoke_uses_central_secret_scan_for_alternative_lockfile(tmp_path):
    (tmp_path / "yarn.lock").write_text(
        'private-package@1.0.0:\n  resolved "https://user:supersecretvalue@registry.example/private.tgz"\n',
        encoding="utf-8",
    )

    result = run_script("-WebsiteRoot", str(tmp_path))

    assert result.returncode != 0
    assert "Potential website secret patterns found by central risky-artifact scanner" in result.stdout
    assert "yarn.lock" in result.stdout

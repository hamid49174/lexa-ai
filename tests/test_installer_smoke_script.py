import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_installer_smoke.ps1"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )


def test_installer_smoke_missing_installer_is_warn_only_by_default(tmp_path):
    result = run_script("-ArtifactRoot", str(tmp_path))

    assert result.returncode == 0, result.stdout
    assert "not yet proven" in result.stdout


def test_installer_smoke_missing_installer_can_be_blocking(tmp_path):
    result = run_script("-ArtifactRoot", str(tmp_path), "-RequireInstaller")

    assert result.returncode != 0
    assert "No installer artifact found" in result.stdout


def test_installer_smoke_blocks_forbidden_content_near_installer(tmp_path):
    installer = tmp_path / "Lexa-Setup.exe"
    installer.write_bytes(b"0" * (2 * 1024 * 1024))
    (tmp_path / "bridge-audit.log").write_text("private", encoding="utf-8")

    result = run_script("-ArtifactRoot", str(tmp_path), "-InstallerPath", str(installer))

    assert result.returncode != 0
    assert "Forbidden content" in result.stdout


def test_installer_smoke_does_not_delete_artifacts(tmp_path):
    installer = tmp_path / "Lexa-Setup.exe"
    installer.write_bytes(b"0" * (2 * 1024 * 1024))

    result = run_script("-ArtifactRoot", str(tmp_path), "-InstallerPath", str(installer), "-AllowUnsignedInternal")

    assert result.returncode == 0, result.stdout
    assert installer.exists()
    assert "Installer smoke completed" in result.stdout
    assert "Signing status:" in result.stdout
    assert "Target: InternalRC" in result.stdout


def test_installer_install_requires_vm_only(tmp_path):
    installer = tmp_path / "Lexa-Setup.exe"
    installer.write_bytes(b"0" * (2 * 1024 * 1024))

    result = run_script("-ArtifactRoot", str(tmp_path), "-InstallerPath", str(installer), "-Install")

    assert result.returncode != 0
    assert "requires -VMOnly" in result.stdout


def test_installer_vm_only_install_is_not_auto_executed(tmp_path):
    installer = tmp_path / "Lexa-Setup.exe"
    installer.write_bytes(b"0" * (2 * 1024 * 1024))

    result = run_script("-ArtifactRoot", str(tmp_path), "-InstallerPath", str(installer), "-Install", "-Uninstall", "-VMOnly")

    assert result.returncode == 0, result.stdout
    assert "not executed automatically" in result.stdout
    assert "not yet proven" in result.stdout
    assert "Installer VM install/uninstall plan" in result.stdout
    assert "VM test marker LEXA_INSTALLER_VM_TEST" in result.stdout


def test_installer_plan_only_prints_vm_plan():
    result = run_script("-PlanOnly")

    assert result.returncode == 0, result.stdout
    assert "Installer VM install/uninstall plan" in result.stdout
    assert "Plan-only mode" in result.stdout
    assert "Windows Sandbox available:" in result.stdout
    assert "Hyper-V available:" in result.stdout
    assert "VM test marker LEXA_INSTALLER_VM_TEST:" in result.stdout


def test_unsigned_installer_blocks_public_rc(tmp_path):
    installer = tmp_path / "Lexa-Setup.exe"
    installer.write_bytes(b"0" * (2 * 1024 * 1024))

    result = run_script(
        "-ArtifactRoot",
        str(tmp_path),
        "-InstallerPath",
        str(installer),
        "-Target",
        "PublicRC",
    )

    assert result.returncode != 0
    assert "blocks PublicRC" in result.stdout


def test_unsigned_installer_blocks_public_release(tmp_path):
    installer = tmp_path / "Lexa-Setup.exe"
    installer.write_bytes(b"0" * (2 * 1024 * 1024))

    result = run_script(
        "-ArtifactRoot",
        str(tmp_path),
        "-InstallerPath",
        str(installer),
        "-Target",
        "PublicRelease",
    )

    assert result.returncode != 0
    assert "blocks PublicRelease" in result.stdout


def test_installer_accepts_expected_publisher_parameter_for_internal_rc(tmp_path):
    installer = tmp_path / "Lexa-Setup.exe"
    installer.write_bytes(b"0" * (2 * 1024 * 1024))

    result = run_script(
        "-ArtifactRoot",
        str(tmp_path),
        "-InstallerPath",
        str(installer),
        "-ExpectedPublisher",
        "Lexa",
        "-AllowUnsignedInternal",
    )

    assert result.returncode == 0, result.stdout
    assert "ExpectedPublisher: Lexa" in result.stdout

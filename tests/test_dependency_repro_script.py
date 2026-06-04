import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_dependency_repro.ps1"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )


def write_minimal_repo(repo_root: Path) -> None:
    repo_root.mkdir()
    (repo_root / "requirements.txt").write_text("", encoding="utf-8")
    (repo_root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")


def test_dependency_repro_does_not_report_optional_lockfile_without_package(tmp_path):
    repo_root = tmp_path / "repo"
    website_root = tmp_path / "website"
    os_root = tmp_path / "OS"
    write_minimal_repo(repo_root)
    (repo_root / "frontend").mkdir()
    (repo_root / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (repo_root / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
    website_root.mkdir()
    os_root.mkdir()

    result = run_script(
        "-RepoRoot",
        str(repo_root),
        "-WebsiteRoot",
        str(website_root),
        "-OSRoot",
        str(os_root),
    )

    assert result.returncode == 0, result.stdout
    assert "optional missing: website package.json" not in result.stdout
    assert "optional missing: website lockfile" not in result.stdout
    assert r"optional missing: 00_System\SDK\os-sdk package.json" not in result.stdout
    assert r"optional missing: 11_Integrations\MCP\os-mcp-server package.json" not in result.stdout
    assert r"optional missing: 07_Automations\Workflows\raw-inbox-worker package.json" not in result.stdout
    assert "missing: website" not in result.stdout


def test_dependency_repro_warns_for_lockfile_without_package(tmp_path):
    repo_root = tmp_path / "repo"
    website_root = tmp_path / "website"
    os_root = tmp_path / "OS"
    write_minimal_repo(repo_root)
    (repo_root / "frontend").mkdir()
    (repo_root / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (repo_root / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
    website_root.mkdir()
    (website_root / "yarn.lock").write_text("# yarn lockfile\n", encoding="utf-8")
    os_root.mkdir()

    result = run_script(
        "-RepoRoot",
        str(repo_root),
        "-WebsiteRoot",
        str(website_root),
        "-OSRoot",
        str(os_root),
    )

    assert result.returncode == 0, result.stdout
    assert "website lockfile exists without package.json" in result.stdout
    assert "yarn.lock" in result.stdout


def test_dependency_repro_rejects_directory_named_package_json(tmp_path):
    repo_root = tmp_path / "repo"
    website_root = tmp_path / "website"
    os_root = tmp_path / "OS"
    write_minimal_repo(repo_root)
    (repo_root / "frontend").mkdir()
    (repo_root / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (repo_root / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
    website_root.mkdir()
    (website_root / "package.json").mkdir()
    (website_root / "package-lock.json").write_text("{}", encoding="utf-8")
    os_root.mkdir()

    result = run_script(
        "-RepoRoot",
        str(repo_root),
        "-WebsiteRoot",
        str(website_root),
        "-OSRoot",
        str(os_root),
    )

    assert result.returncode == 0, result.stdout
    assert "not a file: website package.json" in result.stdout
    assert "package.json" in result.stdout


def test_dependency_repro_warns_for_optional_package_without_lockfile(tmp_path):
    repo_root = tmp_path / "repo"
    website_root = tmp_path / "website"
    os_root = tmp_path / "OS"
    write_minimal_repo(repo_root)
    (repo_root / "frontend").mkdir()
    (repo_root / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (repo_root / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
    website_root.mkdir()
    (website_root / "package.json").write_text("{}", encoding="utf-8")
    os_root.mkdir()

    result = run_script(
        "-RepoRoot",
        str(repo_root),
        "-WebsiteRoot",
        str(website_root),
        "-OSRoot",
        str(os_root),
    )

    assert result.returncode == 0, result.stdout
    assert "missing: website lockfile for package.json" in result.stdout
    assert "package-lock.json" in result.stdout


def test_dependency_repro_rejects_directory_named_lockfile(tmp_path):
    repo_root = tmp_path / "repo"
    website_root = tmp_path / "website"
    os_root = tmp_path / "OS"
    write_minimal_repo(repo_root)
    (repo_root / "frontend").mkdir()
    (repo_root / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (repo_root / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
    website_root.mkdir()
    (website_root / "package.json").write_text("{}", encoding="utf-8")
    (website_root / "package-lock.json").mkdir()
    os_root.mkdir()

    result = run_script(
        "-RepoRoot",
        str(repo_root),
        "-WebsiteRoot",
        str(website_root),
        "-OSRoot",
        str(os_root),
    )

    assert result.returncode == 0, result.stdout
    assert "website lockfile path is not a file: package-lock.json" in result.stdout
    assert "ok: website lockfile" not in result.stdout


def test_dependency_repro_rejects_directory_named_required_file(tmp_path):
    repo_root = tmp_path / "repo"
    website_root = tmp_path / "website"
    os_root = tmp_path / "OS"
    write_minimal_repo(repo_root)
    (repo_root / "requirements.txt").unlink()
    (repo_root / "requirements.txt").mkdir()
    (repo_root / "frontend").mkdir()
    (repo_root / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (repo_root / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
    website_root.mkdir()
    os_root.mkdir()

    result = run_script(
        "-RepoRoot",
        str(repo_root),
        "-WebsiteRoot",
        str(website_root),
        "-OSRoot",
        str(os_root),
    )

    assert result.returncode == 0, result.stdout
    assert "not a file: Python requirements" in result.stdout
    assert "requirements.txt" in result.stdout

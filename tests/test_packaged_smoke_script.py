import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGING_SCRIPT = REPO_ROOT / "scripts" / "run_packaging_smoke.ps1"


def read_script() -> str:
    return (REPO_ROOT / "scripts" / "smoke_packaged.ps1").read_text(encoding="utf-8")


def write_minimal_packaging_repo(
    repo_root: Path,
    extra_resources: list[dict],
    extra_config: dict | None = None,
    package_scripts: dict | None = None,
    package_lock: dict | None = None,
    extra_frontend_files: dict[str, str] | None = None,
) -> None:
    frontend = repo_root / "frontend"
    frontend.mkdir(parents=True)
    config = {
        "files": ["main.js"],
        "extraResources": [
            {
                "from": "../backend-dist/lexa-backend",
                "to": "backend-dist",
                "filter": [
                    "**/*",
                    "!**/audit.log",
                    "!**/bridge-audit.log",
                    "!**/lexa_memory.db*",
                ],
            },
            *extra_resources,
        ],
    }
    if extra_config:
        config.update(extra_config)
    (frontend / "package.json").write_text(
        json.dumps({"scripts": package_scripts or {"build": "echo build"}}),
        encoding="utf-8",
    )
    if package_lock is not None:
        (frontend / "package-lock.json").write_text(
            json.dumps(package_lock),
            encoding="utf-8",
        )
    if extra_frontend_files:
        for relative_name, text in extra_frontend_files.items():
            extra_path = frontend / relative_name
            extra_path.parent.mkdir(parents=True, exist_ok=True)
            extra_path.write_text(text, encoding="utf-8")
    (frontend / "electron-builder.json").write_text(
        json.dumps(config),
        encoding="utf-8",
    )


def run_packaging_smoke(repo_root: Path, artifact_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACKAGING_SCRIPT),
            "-RepoRoot",
            str(repo_root),
            "-ArtifactRoot",
            str(artifact_root),
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )


def test_packaged_smoke_does_not_kill_preexisting_lexa_processes():
    src = read_script()

    assert "Get-LexaPackagedSmokeProcesses" in src
    assert "$baselineProcessIds" in src
    assert "$baselineProcessIds.ContainsKey([int]$_.ProcessId)" in src
    assert "$ownedProcessIds.ContainsKey([int]$_.ProcessId)" in src
    assert "Stop-Process -Id $_.ProcessId" in src
    assert "} | Stop-Process -Force" not in src


def test_packaged_smoke_blocks_preexisting_health_endpoint():
    src = read_script()

    assert "Invoke-LexaPackagedHealthProbe" in src
    assert "Port 8000 already answered /health before packaged app start" in src
    assert "http://127.0.0.1:8000/health" in src


def test_packaged_smoke_launches_hidden_packaged_app():
    src = read_script()

    assert "Start-Process -FilePath $AppPath" in src
    assert "-WindowStyle Hidden" in src
    assert "-PassThru" in src


def test_packaging_build_runs_packaged_runtime_smoke():
    src = (REPO_ROOT / "scripts" / "run_packaging_smoke.ps1").read_text(encoding="utf-8")

    assert "win-unpacked\\Lexa AI.exe" in src
    assert "smoke_packaged.ps1" in src
    assert "-AppPath $packagedApp" in src
    assert "-TimeoutSeconds 45" in src
    assert "electron-builder failed with exit code" in src
    assert "Packaged runtime smoke failed with exit code" in src


def test_packaging_smoke_blocks_isolated_dist_build_artifacts_from_staging():
    src = (REPO_ROOT / "scripts" / "run_packaging_smoke.ps1").read_text(encoding="utf-8")

    assert '"dist-*-build"' in src


def test_packaging_smoke_cleans_generated_temp_artifacts_only_after_success():
    src = (REPO_ROOT / "scripts" / "run_packaging_smoke.ps1").read_text(encoding="utf-8")

    assert "[switch]$KeepArtifactRoot" in src
    assert "$generatedArtifactRoot = $true" in src
    assert "StartsWith($tempRoot" in src
    assert "Refusing to clean generated artifact root outside temp" in src
    assert "Remove-Item -LiteralPath $resolvedArtifactRoot -Recurse -Force" in src
    assert "generated artifact root cleaned" in src


def test_packaging_smoke_runs_central_risky_artifact_check():
    src = (REPO_ROOT / "scripts" / "run_packaging_smoke.ps1").read_text(encoding="utf-8")

    assert "Invoke-RiskyArtifactPathCheck" in src
    assert "Invoke-RiskySecretScanPathCheck" in src
    assert "check_risky_artifacts.ps1" in src
    assert "Test-Path -LiteralPath $PathValue -PathType Leaf" in src
    assert "-ArtifactPath $PathValue" in src
    assert "-SecretScanPath $PathValue" in src
    assert "$packageSecretScanPaths = @(" in src
    assert "package-lock.json" in src
    assert "npm-shrinkwrap.json" in src
    assert "yarn.lock" in src
    assert "pnpm-lock.yaml" in src
    assert "foreach ($packageSecretScanPath in $packageSecretScanPaths)" in src
    assert "Invoke-RiskySecretScanPathCheck $packageSecretScanPath" in src
    assert "Invoke-RiskySecretScanPathCheck $builderConfig" in src


def test_packaging_smoke_rejects_directory_named_package_json(tmp_path):
    repo_root = tmp_path / "repo"
    frontend = repo_root / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").mkdir()
    (frontend / "electron-builder.json").write_text(
        json.dumps({"files": ["main.js"], "extraResources": []}),
        encoding="utf-8",
    )

    result = run_packaging_smoke(repo_root, tmp_path / "artifacts")

    assert result.returncode != 0
    assert "frontend package.json is not a file" in result.stdout


def test_packaging_smoke_blocks_credential_and_signing_config_paths_static():
    src = (REPO_ROOT / "scripts" / "run_packaging_smoke.ps1").read_text(encoding="utf-8")

    assert "$riskyConfigPathRegex" in src
    assert "ConvertTo-RiskyConfigScanText" in src
    assert "$builderRiskScanJson -match $riskyConfigPathRegex" in src
    assert "credentials|secrets" in src
    assert "client_secret" in src
    assert "service[-_]?" in src
    assert "pfx|p12|pem|ppk|key|pvk|cer|crt|spc|jks|keystore" in src
    assert "signing|signtool" in src


def test_packaging_smoke_blocks_credential_config_reference(tmp_path):
    repo_root = tmp_path / "repo"
    write_minimal_packaging_repo(
        repo_root,
        [{"from": "../config/credentials.json", "to": "credentials.json"}],
    )

    result = run_packaging_smoke(repo_root, tmp_path / "artifacts")

    assert result.returncode != 0
    assert "credential, or signing paths" in result.stdout


def test_packaging_smoke_blocks_signing_path_outside_resource_lists(tmp_path):
    repo_root = tmp_path / "repo"
    write_minimal_packaging_repo(
        repo_root,
        [],
        {"win": {"certificateFile": "../release/windows-signing.pfx"}},
    )

    result = run_packaging_smoke(repo_root, tmp_path / "artifacts")

    assert result.returncode != 0
    assert "credential, or signing paths" in result.stdout


def test_packaging_smoke_blocks_inline_builder_config_secret(tmp_path):
    repo_root = tmp_path / "repo"
    write_minimal_packaging_repo(
        repo_root,
        [],
        {"win": {"certificatePassword": "supersecretvalue"}},
    )

    result = run_packaging_smoke(repo_root, tmp_path / "artifacts")

    assert result.returncode != 0
    assert "Risky secret scan failed" in result.stdout


def test_packaging_smoke_blocks_inline_package_script_secret(tmp_path):
    repo_root = tmp_path / "repo"
    write_minimal_packaging_repo(
        repo_root,
        [],
        package_scripts={
            "build": "echo build",
            "publish": "deploy --credential supersecretvalue",
        },
    )

    result = run_packaging_smoke(repo_root, tmp_path / "artifacts")

    assert result.returncode != 0
    assert "Risky secret scan failed" in result.stdout
    assert "package.json" in result.stdout


def test_packaging_smoke_blocks_package_lock_url_credentials(tmp_path):
    repo_root = tmp_path / "repo"
    write_minimal_packaging_repo(
        repo_root,
        [],
        package_lock={
            "name": "lexa-fixture",
            "packages": {
                "": {"dependencies": {"private-package": "1.0.0"}},
                "node_modules/private-package": {
                    "resolved": "https://registry-user:supersecretvalue@registry.example/private-package.tgz"
                },
            },
        },
    )

    result = run_packaging_smoke(repo_root, tmp_path / "artifacts")

    assert result.returncode != 0
    assert "Risky secret scan failed" in result.stdout
    assert "package-lock.json" in result.stdout


def test_packaging_smoke_blocks_alternative_lockfile_url_credentials(tmp_path):
    repo_root = tmp_path / "repo"
    write_minimal_packaging_repo(
        repo_root,
        [],
        extra_frontend_files={
            "pnpm-lock.yaml": (
                "packages:\n"
                "  /private-package@1.0.0:\n"
                '    resolution: {tarball: "https://registry-user:supersecretvalue@registry.example/private-package.tgz"}\n'
            )
        },
    )

    result = run_packaging_smoke(repo_root, tmp_path / "artifacts")

    assert result.returncode != 0
    assert "Risky secret scan failed" in result.stdout
    assert "pnpm-lock.yaml" in result.stdout

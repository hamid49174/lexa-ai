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


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=True,
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


def test_warn_mode_reports_risky_staged_file_without_blocking(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text("personal_os/private.md\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged), "-Mode", "Warn")

    assert result.returncode == 0, result.stdout
    assert "Risky staged path" in result.stdout
    assert "Risky artifact check completed with warnings" in result.stdout
    assert "Warnings: 1" in result.stdout
    assert "Mode: Warn" in result.stdout


def test_isolated_dist_build_output_is_blocked_from_staging(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text("dist-verify-build/win-unpacked/Lexa AI.exe\n", encoding="utf-8")

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


def test_warn_mode_reports_secret_scan_without_blocking(tmp_path):
    secret_file = tmp_path / "candidate.env"
    secret_file.write_text("api_key=sk_test_1234567890abcdef\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file), "-Mode", "Warn")

    assert result.returncode == 0, result.stdout
    assert secret_file.exists()
    assert "Secret-like pattern" in result.stdout
    assert "Risky artifact check completed with warnings" in result.stdout
    assert "Warnings: 1" in result.stdout
    assert "Mode: Warn" in result.stdout


def test_secret_scan_path_blocks_authorization_bearer_headers(tmp_path):
    secret_file = tmp_path / "http.log"
    secret_file.write_text("Authorization: Bearer sk_live_1234567890abcdef\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_secret_scan_path_blocks_private_key_blocks(tmp_path):
    secret_file = tmp_path / "notes.md"
    secret_file.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nredacted\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_secret_scan_path_blocks_common_bare_provider_tokens(tmp_path):
    secret_file = tmp_path / "debug.log"
    secret_file.write_text(
        "\n".join(
            [
                "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
                "glpat-1234567890abcdefghij",
                "hf_1234567890abcdefghijklmnopqrst",
                "npm_1234567890abcdefghijklmnopqrst",
                "xoxb-1234567890-abcdefghijklmnopqrst",
                "AKIAIOSFODNN7EXAMPLE",
                "AIza1234567890abcdefghijklmnopqrst",
                "gsk_1234567890abcdefghijklmnopqrst",
                "sk-ant-1234567890abcdefghijklmnopqrst",
                "sk-or-v1-1234567890abcdefghijklmnopqrst",
                "sk_car_1234567890abcdefghijklmnopqrst",
                "sk-proj-1234567890abcdefghijklmnopqrst",
                "sk_live_1234567890abcdef",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_secret_scan_path_blocks_generic_password_fields(tmp_path):
    secret_file = tmp_path / "database.log"
    secret_file.write_text("db_password=supersecretvalue\npassphrase: anothersecretvalue\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_secret_scan_path_blocks_generic_password_fields_with_special_characters(tmp_path):
    secret_file = tmp_path / "database.log"
    secret_file.write_text("db_password=P@ssw0rd!2026\napi_key='abc$def%ghi'\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_secret_scan_path_blocks_structured_json_secret_fields(tmp_path):
    secret_file = tmp_path / "builder.json"
    secret_file.write_text('{"certificatePassword": "supersecretvalue"}\n', encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_secret_scan_path_blocks_structured_json_credential_fields(tmp_path):
    secret_file = tmp_path / "runtime.json"
    secret_file.write_text(
        '{"serviceRoleKey": "supersecretvalue", "credential": "anothersecretvalue"}\n',
        encoding="utf-8",
    )

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_secret_scan_path_blocks_quoted_secret_values_with_spaces(tmp_path):
    secret_file = tmp_path / "phrases.env"
    secret_file.write_text(
        'db_password="correct horse battery staple"\napi_key=\'words with spaces secret\'\n',
        encoding="utf-8",
    )

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_secret_scan_path_blocks_cli_secret_flags(tmp_path):
    secret_file = tmp_path / "commands.log"
    secret_file.write_text(
        'lexa sync --api-key sk-proj-1234567890abcdefghijklmnopqrst\n'
        'deploy --credential supersecretvalue\n'
        'deploy --password "correct horse battery staple"\n'
        "tool /token supersecretvalue\n",
        encoding="utf-8",
    )

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_secret_scan_path_blocks_url_embedded_credentials(tmp_path):
    secret_file = tmp_path / "lockfile.json"
    secret_file.write_text(
        '{"resolved": "https://registry-user:supersecretvalue@registry.example/pkg.tgz"}\n',
        encoding="utf-8",
    )

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_secret_scan_path_blocks_lexa_license_keys(tmp_path):
    secret_file = tmp_path / "license.log"
    secret_file.write_text("activated license LEXA-ABCDE-12345-F00D1-BEEF0\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 1
    assert "Secret-like pattern" in result.stdout


def test_secret_scan_path_allows_lexa_license_placeholder(tmp_path):
    secret_file = tmp_path / "license.example"
    secret_file.write_text("LEXA_LICENSE_SMOKE_KEY=LEXA-00000-00000-00000-00000\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-SecretScanPath", str(secret_file))

    assert result.returncode == 0, result.stdout
    assert "Risky artifact check passed" in result.stdout


def test_nested_local_credential_files_warn_without_blocking(tmp_path):
    run_git(tmp_path, "init")
    secret_file = tmp_path / "frontend" / ".npmrc"
    secret_file.parent.mkdir()
    secret_file.write_text("//registry.npmjs.org/:_authToken=supersecretvalue\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path))

    assert result.returncode == 0, result.stdout
    assert "Risky local path present" in result.stdout
    assert "frontend/.npmrc" in result.stdout
    assert "Risky artifact check completed with warnings" in result.stdout
    assert "Warnings: 1" in result.stdout


def test_nested_local_signing_and_cloud_files_warn_without_blocking(tmp_path):
    run_git(tmp_path, "init")
    signing_file = tmp_path / "release" / "windows_signing.pem"
    signing_file.parent.mkdir()
    signing_file.write_text("placeholder", encoding="utf-8")
    cloud_file = tmp_path / "config" / ".aws" / "credentials"
    cloud_file.parent.mkdir(parents=True)
    cloud_file.write_text("aws_access_key_id=AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path))

    assert result.returncode == 0, result.stdout
    assert "Risky local path present" in result.stdout
    assert "release/windows_signing.pem" in result.stdout
    assert "config/.aws/credentials" in result.stdout
    assert "Risky artifact check completed with warnings" in result.stdout
    assert "Warnings: 2" in result.stdout


def test_artifact_path_blocks_user_data(tmp_path):
    artifact = tmp_path / "dist"
    artifact.mkdir()
    (artifact / "lexa_memory.db").write_text("not real sqlite", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-ArtifactPath", str(artifact))

    assert result.returncode == 1
    assert "Forbidden file" in result.stdout or "Risky" in result.stdout


def test_artifact_path_blocks_single_risky_file(tmp_path):
    signing_file = tmp_path / "windows-signing.pfx"
    signing_file.write_bytes(b"0" * 1024)

    result = run_script("-Root", str(tmp_path), "-ArtifactPath", str(signing_file))

    assert result.returncode == 1
    assert "Forbidden file" in result.stdout
    assert "windows-signing.pfx" in result.stdout


def test_artifact_path_blocks_single_contextual_credential_file(tmp_path):
    credential_file = tmp_path / ".aws" / "credentials"
    credential_file.parent.mkdir()
    credential_file.write_text("aws_access_key_id=placeholder\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-ArtifactPath", str(credential_file))

    assert result.returncode == 1
    assert "Forbidden file" in result.stdout
    assert ".aws" in result.stdout
    assert "credentials" in result.stdout


def test_artifact_path_allows_pyinstaller_certifi_ca_bundle(tmp_path):
    ca_bundle = tmp_path / "win-unpacked" / "resources" / "backend-dist" / "_internal" / "certifi" / "cacert.pem"
    ca_bundle.parent.mkdir(parents=True)
    ca_bundle.write_text("-----BEGIN CERTIFICATE-----\npublic-ca-bundle\n-----END CERTIFICATE-----\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-ArtifactPath", str(tmp_path))

    assert result.returncode == 0, result.stdout
    assert "Risky artifact check passed" in result.stdout


def test_artifact_path_blocks_contextual_credential_directory_root(tmp_path):
    artifact = tmp_path / ".docker"
    artifact.mkdir()
    (artifact / "config.json").write_text('{"auths": {}}\n', encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-ArtifactPath", str(artifact))

    assert result.returncode == 1
    assert "Forbidden file" in result.stdout
    assert ".docker" in result.stdout
    assert "config.json" in result.stdout


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


def test_package_manager_credential_files_are_blocked_from_staging(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text(
        ".netrc\n.npmrc\n.pnpmrc\nrelease/.pypirc\n.yarnrc\n.yarnrc.yml\npip.conf\nconfig/pip.ini\n",
        encoding="utf-8",
    )

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Risky staged path" in result.stdout


def test_cloud_and_container_credential_files_are_blocked_from_staging(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text(
        "\n".join(
            [
                ".aws/credentials",
                ".aws/config",
                ".azure/accessTokens.json",
                ".azure/azureProfile.json",
                ".config/gcloud/application_default_credentials.json",
                ".docker/config.json",
                ".gcloud/application_default_credentials.json",
                ".kube/config",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Risky staged path" in result.stdout


def test_generic_machine_credential_files_are_blocked_from_staging(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text(
        "\n".join(
            [
                "credentials.json",
                "config/secrets.yaml",
                "release/client_secret_google.json",
                "release/service-account-prod.json",
                "release/service_account_prod.json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Risky staged path" in result.stdout


def test_nested_local_generic_credential_files_warn_without_blocking(tmp_path):
    run_git(tmp_path, "init")
    secret_file = tmp_path / "config" / "service-account-prod.json"
    secret_file.parent.mkdir()
    secret_file.write_text('{"private_key": "placeholder"}\n', encoding="utf-8")
    yaml_file = tmp_path / "config" / "credentials.yaml"
    yaml_file.write_text("token: placeholder\n", encoding="utf-8")
    toml_file = tmp_path / "config" / "secrets.toml"
    toml_file.write_text('token = "placeholder"\n', encoding="utf-8")

    result = run_script("-Root", str(tmp_path))

    assert result.returncode == 0, result.stdout
    assert "Risky local path present" in result.stdout
    assert "config/service-account-prod.json" in result.stdout
    assert "config/credentials.yaml" in result.stdout
    assert "config/secrets.toml" in result.stdout
    assert "Risky artifact check completed with warnings" in result.stdout
    assert "Warnings: 3" in result.stdout


def test_ssh_private_key_files_are_blocked_from_staging(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text(".ssh/id_rsa\nkeys/id_ed25519\nrelease/windows.ppk\n", encoding="utf-8")

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


def test_env_example_placeholder_is_allowed_from_staging(tmp_path):
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=your_openai_key\n", encoding="utf-8")
    staged = tmp_path / "staged.txt"
    staged.write_text(".env.example\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 0, result.stdout
    assert "Risky artifact check passed" in result.stdout


def test_env_example_with_real_token_is_blocked_from_staging(tmp_path):
    (tmp_path / ".env.example").write_text(
        "OPENAI_API_KEY=sk-proj-1234567890abcdefghijklmnopqrst\n",
        encoding="utf-8",
    )
    staged = tmp_path / "staged.txt"
    staged.write_text(".env.example\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Secret-like value found" in result.stdout
    assert ".env.example" in result.stdout


def test_env_example_with_real_lexa_license_key_is_blocked_from_staging(tmp_path):
    (tmp_path / ".env.example").write_text(
        "LEXA_LICENSE_SMOKE_KEY=LEXA-ABCDE-12345-F00D1-BEEF0\n",
        encoding="utf-8",
    )
    staged = tmp_path / "staged.txt"
    staged.write_text(".env.example\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Secret-like value found" in result.stdout
    assert ".env.example" in result.stdout


def test_env_example_with_generic_secret_value_is_blocked_from_staging(tmp_path):
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=supersecretvalue\n", encoding="utf-8")
    staged = tmp_path / "staged.txt"
    staged.write_text(".env.example\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Secret-like value found" in result.stdout
    assert ".env.example" in result.stdout


def test_env_example_with_exported_generic_secret_value_is_blocked_from_staging(tmp_path):
    (tmp_path / ".env.example").write_text("export OPENAI_API_KEY=supersecretvalue\n", encoding="utf-8")
    staged = tmp_path / "staged.txt"
    staged.write_text(".env.example\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Secret-like value found" in result.stdout
    assert ".env.example" in result.stdout


def test_env_example_with_windows_cmd_secret_value_is_blocked_from_staging(tmp_path):
    (tmp_path / ".env.example").write_text("set OPENAI_API_KEY=supersecretvalue\n", encoding="utf-8")
    staged = tmp_path / "staged.txt"
    staged.write_text(".env.example\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Secret-like value found" in result.stdout
    assert ".env.example" in result.stdout


def test_env_example_with_powershell_secret_value_is_blocked_from_staging(tmp_path):
    (tmp_path / ".env.example").write_text("$env:OPENAI_API_KEY=supersecretvalue\n", encoding="utf-8")
    staged = tmp_path / "staged.txt"
    staged.write_text(".env.example\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Secret-like value found" in result.stdout
    assert ".env.example" in result.stdout


def test_env_example_with_commented_generic_secret_value_is_blocked_from_staging(tmp_path):
    (tmp_path / ".env.example").write_text("# STRIPE_SECRET_KEY=supersecretvalue\n", encoding="utf-8")
    staged = tmp_path / "staged.txt"
    staged.write_text(".env.example\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Secret-like value found" in result.stdout
    assert ".env.example" in result.stdout


def test_env_example_with_credential_value_is_blocked_from_staging(tmp_path):
    (tmp_path / ".env.example").write_text("SERVICE_CREDENTIAL=supersecretvalue\n", encoding="utf-8")
    staged = tmp_path / "staged.txt"
    staged.write_text(".env.example\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path), "-StagedFileList", str(staged))

    assert result.returncode == 1
    assert "Secret-like value found" in result.stdout
    assert ".env.example" in result.stdout


def test_env_example_scan_reads_staged_blob_before_worktree(tmp_path):
    run_git(tmp_path, "init")
    env_example = tmp_path / ".env.example"
    env_example.write_text("OPENAI_API_KEY=supersecretvalue\n", encoding="utf-8")
    run_git(tmp_path, "add", ".env.example")
    env_example.write_text("OPENAI_API_KEY=your_openai_key\n", encoding="utf-8")

    result = run_script("-Root", str(tmp_path))

    assert result.returncode == 1
    assert "Secret-like value found" in result.stdout
    assert ".env.example" in result.stdout

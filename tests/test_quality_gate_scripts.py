import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def quality_gate_risky_staged_pattern() -> re.Pattern[str]:
    src = read("scripts/run_quality_gates.ps1")
    match = re.search(r"(?m)^\$RiskyStagedPattern = '(.+)'$", src)
    assert match, "Risky staged pattern assignment not found"
    return re.compile(match.group(1))


def test_quality_gates_include_release_script_tests_and_startup_smoke():
    src = read("scripts/run_quality_gates.ps1")

    assert "test_release_candidate_check.py" in src
    assert "test_backend_data_dir_static.py" in src
    assert "test_build_backend_script.py" in src
    assert "test_clean_temp_safety.py" in src
    assert "test_remote_ci_readiness_script.py" in src
    assert "test_codex_context_pack.py" in src
    assert "test_quality_gate_scripts.py" in src
    assert "test_dependency_repro_script.py" in src
    assert "test_performance_budgets.py" in src
    assert "test_risky_artifact_check.py" in src
    assert "test_clean_clone_smoke_script.py" in src
    assert "test_installer_smoke_script.py" in src
    assert "test_packaged_smoke_script.py" in src
    assert "test_packaging_config_static.py" in src
    assert "test_start_launcher_static.py" in src
    assert "test_fastapi_lifespan.py" in src
    assert "test_router_stripe_security.py" in src
    assert "test_workflow_templates.py" in src
    assert "Invoke-BackendCoverageSmoke" in src
    assert "--cov=backend" in src
    assert "check_risky_artifacts.ps1" in src
    assert "sync-vendor.cjs" in src
    assert 'Filter "electron_*_smoke.js"' in src
    assert "node $test.FullName" in src
    assert "Electron smoke gate completed" in src
    assert "& $Electron" not in src


def test_quality_gates_support_eval_and_ci_modes():
    src = read("scripts/run_quality_gates.ps1")

    assert 'ValidateSet("Quick", "Full", "Eval", "CI")' in src
    assert 'if ($Mode -eq "Eval")' in src
    assert 'if ($Mode -eq "CI")' in src
    assert "Invoke-EvalRegressionGate" in src
    assert "Invoke-PackagingConfigSmoke" in src
    assert "No .git directory found" in src


def test_quality_gates_risky_git_scan_includes_build_and_cache_outputs():
    src = read("scripts/run_quality_gates.ps1")

    for path in [
        "dist-*-build",
        "backend-dist",
        "frontend/dist",
        "evals/results",
        "tmp/agent_traces",
        ".pytest_cache",
        "audio_cache",
        "node_modules",
        "venv",
    ]:
        assert path in src
    assert "dist-[^/]*build/" in src
    assert "(.*/)?node_modules/" in src


def test_quality_gates_risky_git_scan_includes_secrets_and_signing_material():
    src = read("scripts/run_quality_gates.ps1")

    for path in [
        ".env",
        "*.env",
        ".netrc",
        ".npmrc",
        ".pnpmrc",
        ".pypirc",
        ".yarnrc",
        ".yarnrc.yml",
        ".aws/credentials",
        ".aws/config",
        ".azure/accessTokens.json",
        ".azure/azureProfile.json",
        ".config/gcloud/application_default_credentials.json",
        ".docker/config.json",
        ".gcloud/application_default_credentials.json",
        ".kube/config",
        "credentials.json",
        "credentials.yml",
        "credentials.yaml",
        "credentials.toml",
        "credentials.ini",
        "credentials.conf",
        "secrets.json",
        "secrets.yml",
        "secrets.yaml",
        "secrets.toml",
        "secrets.ini",
        "secrets.conf",
        "client_secret.json",
        "service-account.json",
        "service_account.json",
        ".ssh/id_dsa",
        ".ssh/id_ecdsa",
        ".ssh/id_ed25519",
        ".ssh/id_rsa",
        "pip.conf",
        "pip.ini",
        "*.pfx",
        "*.p12",
        "*.pem",
        "*.ppk",
        "*.key",
        "*.pvk",
        "*.cer",
        "*.crt",
        "*.spc",
        "*.jks",
        "*.keystore",
    ]:
        assert path in src
    assert ".env.*" not in src
    assert "\\.env\\.example" in src
    assert "(.*/)?\\.env($|\\.|/)" in src
    assert "(.*/)?\\.netrc$" in src
    assert "(.*/)?\\.(npmrc|pnpmrc|pypirc)$" in src
    assert "(.*/)?\\.yarnrc(\\.yml)?$" in src
    assert "(.*/)?\\.aws/(credentials|config)$" in src
    assert "(.*/)?\\.azure/(accessTokens|azureProfile)\\.json$" in src
    assert "(.*/)?\\.docker/config\\.json$" in src
    assert "(.*/)?\\.kube/config$" in src
    assert "(.*/)?(credentials|secrets)\\.(json|ya?ml|toml|ini|conf)$" in src
    assert "(.*/)?client_secret[^/]*\\.json$" in src
    assert "(.*/)?service[-_]?account[^/]*\\.json$" in src
    assert "(.*/)?\\.ssh/(id_dsa|id_ecdsa|id_ed25519|id_rsa)$" in src
    assert "(.*/)?(id_dsa|id_ecdsa|id_ed25519|id_rsa)$" in src
    assert "(.*/)?pip\\.(conf|ini)$" in src
    assert ".*\\.(pfx|p12|pem|ppk|key|pvk|cer|crt|spc|jks|keystore)$" in src
    assert "(codesign|code-sign|signing|signtool)" in src
    assert "(windows|electron)[_-]?(signing|certificate|cert)" in src


def test_quality_gates_risky_git_scan_warns_nested_credentials_and_signing_material():
    src = read("scripts/run_quality_gates.ps1")

    for pathspec in [
        ":(glob)**/.npmrc",
        ":(glob)**/.aws/credentials",
        ":(glob)**/.docker/config.json",
        ":(glob)**/credentials.json",
        ":(glob)**/credentials.yaml",
        ":(glob)**/credentials.toml",
        ":(glob)**/secrets.json",
        ":(glob)**/secrets.yaml",
        ":(glob)**/secrets.toml",
        ":(glob)**/client_secret*.json",
        ":(glob)**/service-account*.json",
        ":(glob)**/service_account*.json",
        ":(glob)**/.ssh/id_rsa",
        ":(glob)**/pip.conf",
        ":(glob)**/*.pem",
        ":(glob)**/*.pfx",
        ":(glob)**/*.keystore",
    ]:
        assert pathspec in src


def test_quality_gates_risky_staged_pattern_matches_real_risky_samples():
    pattern = quality_gate_risky_staged_pattern()

    for path in [
        ".env",
        "config/.env.local",
        "release/windows_signing.pfx",
        "release/public-cert.cer",
        "dist-verify-build/win-unpacked/Lexa AI.exe",
        "frontend/node_modules/pkg/index.js",
        "evals/results/current_eval_report.json",
        "tmp/agent_traces/run.jsonl",
        "release/signing-config.json",
        "release/signtool-password.txt",
        "release/windows_signing.xml",
        "release/electron-cert.env",
        ".netrc",
        ".npmrc",
        "frontend/.npmrc",
        ".pnpmrc",
        ".pypirc",
        ".yarnrc",
        ".yarnrc.yml",
        ".aws/credentials",
        ".aws/config",
        ".azure/accessTokens.json",
        ".azure/azureProfile.json",
        ".config/gcloud/application_default_credentials.json",
        ".docker/config.json",
        ".gcloud/application_default_credentials.json",
        ".kube/config",
        "credentials.json",
        "config/secrets.yaml",
        "release/client_secret_google.json",
        "release/service-account-prod.json",
        "release/service_account_prod.json",
        ".ssh/id_rsa",
        "keys/id_ed25519",
        "release/windows.ppk",
        "config/pip.conf",
        "config/pip.ini",
    ]:
        assert pattern.match(path), path

    for path in [
        ".env.example",
        "config/.env.example",
        "backend/main.py",
        "frontend/src/vendor/three.min.js",
        "docs/release/signing_plan.md",
    ]:
        assert not pattern.match(path), path


def test_github_quality_workflow_is_non_deploying_and_secret_free():
    workflow = read(".github/workflows/quality-gates.yml")

    assert "run_quality_gates.ps1 -Mode CI" in workflow
    assert "run_eval_regression_gate.ps1" in workflow
    assert "check_risky_artifacts.ps1" in workflow
    assert "run_packaging_smoke.ps1" in workflow
    assert "run_clean_clone_smoke.ps1 -DryRun" in workflow
    assert "run_release_candidate_check.ps1 -Mode CICore" in workflow
    assert "run_os_quality_gates.ps1 -AllowMissing" in workflow
    assert "actions/upload-artifact" not in workflow
    assert "softprops/action-gh-release" not in workflow
    assert "secrets." not in workflow


def test_remote_ci_readiness_script_exists_and_checks_required_safety():
    src = read("scripts/check_remote_ci_readiness.ps1")

    assert "RemoteCIReady" in src
    assert "github\\.com" in src
    assert "quality-gates.yml" in src
    assert "secrets\\." in src
    assert "upload-artifact" in src
    assert "personal_os" in src
    assert "package-manager credential path" in src
    assert "cloud credential path" in src
    assert "machine credential file" in src
    assert "signing material path" in src
    assert "credentials|secrets" in src
    assert "service[-_]?" in src
    assert "keystore" in src
    assert "run_quality_gates.ps1" in src
    assert "run_release_candidate_check.ps1" in src
    assert "Remove-Item" not in src


def test_dependency_repro_script_is_read_only():
    src = read("scripts/check_dependency_repro.ps1")

    assert "pip install" not in src
    assert "npm install" not in src
    assert "Remove-Item" not in src
    assert "$NodeLockfiles = @(" in src
    assert "Test-NodeLockfileCoverage" in src
    assert "Test-Path -LiteralPath $PathValue -PathType Leaf" in src
    assert "not a file: $Label" in src
    assert "$nonFileLockfiles" in src
    assert "Test-Path -LiteralPath (Join-Path $Directory $_) -PathType Leaf" in src
    assert "Test-Path -LiteralPath $packagePath -PathType Leaf" in src
    assert "not a file: $Label package.json" in src
    assert "$Label lockfile path is not a file" in src
    assert "package-lock.json" in src
    assert "npm-shrinkwrap.json" in src
    assert "yarn.lock" in src
    assert "pnpm-lock.yaml" in src
    assert "multiple $Label lockfiles found" in src
    assert "$Label lockfile exists without package.json" in src
    assert "missing: $Label package.json and lockfile" in src
    assert "missing: $Label lockfile for package.json" in src
    assert 'Test-NodeLockfileCoverage (Join-Path $RepoRoot "frontend") "frontend"' in src
    assert 'Test-NodeLockfileCoverage $WebsiteRoot "website" $false' in src


def test_dependency_repro_discovers_env_and_desktop_os_roots():
    src = read("scripts/check_dependency_repro.ps1")

    assert "Get-OSRootCandidates" in src
    assert "Select-OSRootCandidate" in src
    assert "Get-OSRootScore" in src
    assert "PERSONAL_OS_ROOT" in src
    assert "PERSONAL_OS_SDK_ROOT" in src
    assert "OneDrive - Office\\Desktop\\OS" in src
    assert "00_System\\SDK\\os-sdk" in src
    assert "11_Integrations\\MCP\\os-mcp-server" in src
    assert "07_Automations\\Workflows\\raw-inbox-worker" in src


def test_packaging_smoke_blocks_forbidden_content_and_guards_temp_cleanup():
    src = read("scripts/run_packaging_smoke.ps1")

    assert "electron-builder.json" in src
    assert "personal_os" in src
    assert "lexa_memory.db" in src
    assert "bridge-audit.log" in src
    assert "npx.cmd --no-install electron-builder" in src
    assert "[switch]$KeepArtifactRoot" in src
    assert "StartsWith($tempRoot" in src
    assert "Refusing to clean generated artifact root outside temp" in src
    assert "Remove-Item -LiteralPath $resolvedArtifactRoot -Recurse -Force" in src


def test_installer_smoke_guards_explicit_installer_paths():
    src = read("scripts/run_installer_smoke.ps1")

    assert "ArtifactRootWasProvided" in src
    assert "Invoke-RiskyArtifactPathCheck $installer.FullName" in src
    assert "InstallerPath must point to a .exe, .msi, or .msix artifact" in src
    assert "Add-ArtifactScanRoot $ArtifactRoot" in src
    assert "Add-ArtifactScanRoot $installer.DirectoryName" in src
    assert "foreach ($artifactScanRoot in $artifactScanRoots)" in src
    assert "credentials, signing material" in src
    assert "Remove-Item" not in src
    assert "git add" not in src.lower()


def test_eval_regression_gate_uses_unique_temp_paths():
    src = read("scripts/run_eval_regression_gate.ps1")

    assert "[System.IO.Path]::GetTempPath()" in src
    assert "[guid]::NewGuid()" in src
    assert "$RunId-current_eval_report.json" in src
    assert "current_eval_report.json" in src


def test_os_hermes_and_website_smokes_are_non_destructive():
    for script in [
        "scripts/run_os_quality_gates.ps1",
        "scripts/run_hermes_smoke.ps1",
        "scripts/run_website_smoke.ps1",
    ]:
        src = read(script)
        assert "Remove-Item" not in src
        assert "git add" not in src.lower()


def test_hermes_smoke_warns_through_central_risky_artifact_check():
    src = read("scripts/run_hermes_smoke.ps1")

    assert "check_risky_artifacts.ps1" in src
    assert "-Root $hermesWorkspace" in src
    assert "-Mode Warn" in src
    assert "-ArtifactPath $hermesWorkspace" in src
    assert "Hermes workspace risky artifact check failed" in src


def test_os_quality_gate_discovers_env_and_desktop_os_roots():
    src = read("scripts/run_os_quality_gates.ps1")

    assert "Get-OSRootCandidates" in src
    assert "Select-OSRootCandidate" in src
    assert "Get-OSRootScore" in src
    assert "PERSONAL_OS_ROOT" in src
    assert "PERSONAL_OS_SDK_ROOT" in src
    assert "OneDrive - Office\\Desktop\\OS" in src
    assert "OneDrive\\Desktop\\OS" in src
    assert "Desktop\\OS" in src
    assert "00_System\\SDK\\os-sdk" in src
    assert "11_Integrations\\MCP\\os-mcp-server" in src
    assert "07_Automations\\Workflows\\raw-inbox-worker" in src


def test_website_smoke_has_target_aware_public_rc_blocking():
    src = read("scripts/run_website_smoke.ps1")

    assert 'ValidateSet("InternalRC", "PublicRC", "PublicRelease")' in src
    assert "Website static-external target without package-based build/lint proof blocks" in src
    assert 'Invoke-NpmScript "lint" "Website lint"' in src
    assert "$LASTEXITCODE" in src
    assert "Website config placeholders block" in src
    assert "Test-DeployableWebsiteRuntimeConfig" in src
    assert "SUPABASE_ANON_KEY" in src
    assert "STRIPE_PUBLISHABLE_KEY" in src
    assert "pro_monthly" in src
    assert "config.runtime.js" in src
    assert "config.runtime.example.js" in src
    assert "Website unsupported external scripts block" in src
    assert "js\\.stripe\\.com/v3" in src
    assert "allowedExternalResourcePatterns" in src
    assert "splinetool/runtime" in src
    assert "prod\\.spline\\.design" in src
    assert "Website unsupported external resources block" in src
    assert "websiteSecretPathRegex" in src
    assert "Invoke-RiskyWebsiteSecretScanPathCheck" in src
    assert "check_risky_artifacts.ps1" in src
    assert "-SecretScanPath $PathValues" in src
    assert "$websiteSecretScanPaths.Add($_.FullName)" in src
    assert "$packageSecretScanPaths = @(" in src
    assert "$packageLock = Join-Path $WebsiteRoot \"package-lock.json\"" in src
    assert "npm-shrinkwrap.json" in src
    assert "yarn.lock" in src
    assert "pnpm-lock.yaml" in src
    assert "Invoke-RiskyWebsiteSecretScanPathCheck @($packageSecretScanPaths | Where-Object" in src
    assert "Test-Path -LiteralPath $_ -PathType Leaf" in src
    assert "credentials|secrets" in src
    assert "service[-_]?account" in src
    assert ".npmrc" in src
    assert "keystore" in src
    assert "cspCriticalPages" in src
    assert "Content-Security-Policy" in src
    assert "style-src 'self'" in src
    assert "unsafe-inline" in src
    assert "Website HTML contains inline script/style/event handlers" in src
    assert "innerHTML" in src
    assert "insertAdjacentHTML" in src
    assert "inline style mutations" in src
    assert "setSafeI18nHtml" in src
    assert "appendSafeI18nNode" in src


def test_paid_license_smoke_is_env_driven_and_non_destructive():
    src = read("scripts/run_paid_license_smoke.ps1")

    assert "LEXA_LICENSE_SMOKE_KEY" in src
    assert "LEXA_LICENSE_SMOKE_API_URL" in src
    assert "LEXA_LICENSE_SMOKE_EXPECTED_PLAN" in src
    assert "Invoke-RestMethod" in src
    assert "/license/validate" in src
    assert "-Method Post" in src
    assert "X-Lexa-Local-Token" in src
    assert "license_key" in src
    assert "Format-MaskedLicenseKey" in src
    assert "AllowMissing" in src
    assert "Remove-Item" not in src
    assert "git add" not in src.lower()


def test_release_candidate_check_has_paid_license_smoke_gate():
    src = read("scripts/run_release_candidate_check.ps1")

    assert "Invoke-PaidLicenseSmokeForTarget" in src
    assert "run_paid_license_smoke.ps1" in src
    assert "LEXA_LICENSE_SMOKE_KEY" in src
    assert "paid_license_smoke" in src
    assert "Paid License Smoke" in src


def test_release_candidate_check_detects_ignored_website_runtime_config():
    src = read("scripts/run_release_candidate_check.ps1")

    assert "Test-WebsitePublicConfigResolved" in src
    assert "website_public_config" in src
    assert "config.runtime.js" in src
    assert "window\\.LEXA_CONFIG" in src
    assert "YOUR_PROJECT" in src
    assert "pk_(live|test)_YOUR" in src
    assert "SUPABASE_ANON_KEY" in src
    assert "STRIPE_PUBLISHABLE_KEY" in src
    assert "pro_monthly" in src


def test_context_pack_generator_is_non_destructive():
    src = read("scripts/generate_codex_context_pack.ps1")

    assert "personal_os" in src
    assert "evals" in src and "results" in src
    assert "Remove-Item" not in src
    assert "public_rc_blocker_matrix.md" in src
    assert "privacy_trace_consent_checklist.md" in src
    assert "agent-solvable" in src


def test_risky_artifact_check_blocks_signtool_password_patterns():
    src = read("scripts/check_risky_artifacts.ps1")

    assert "signtoolSecretRegex" in src
    assert "signtool" in src
    assert "\\s/p\\s+" in src


def test_risky_artifact_check_blocks_cli_secret_flags():
    src = read("scripts/check_risky_artifacts.ps1")

    assert "cliSecretRegex" in src
    assert "--?(api[_-]?key|access[_-]?key|service[_-]?role[_-]?key|token|credential|secret|password|passphrase|passwd|private[_-]?key)" in src
    assert "/(token|credential|secret|password|passphrase|passwd)" in src
    assert "$text -match $cliSecretRegex" in src
    assert "urlCredentialRegex" in src
    assert "$text -match $urlCredentialRegex" in src


def test_risky_artifact_check_blocks_generic_password_fields():
    src = read("scripts/check_risky_artifacts.ps1")

    assert "password|passphrase|passwd" in src
    assert '[^\\s"\'\']{8,}' in src
    assert "quotedSecretRegex" in src
    assert '[^"\'\'\\r\\n]{8,}' in src


def test_risky_artifact_check_blocks_authorization_bearer_headers():
    src = read("scripts/check_risky_artifacts.ps1")

    assert "bearerSecretRegex" in src
    assert "Authorization\\s*:\\s*Bearer" in src


def test_risky_artifact_check_blocks_private_key_blocks():
    src = read("scripts/check_risky_artifacts.ps1")

    assert "privateKeyBlockRegex" in src
    assert "BEGIN (RSA |DSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY" in src


def test_risky_artifact_check_blocks_common_bare_provider_tokens():
    src = read("scripts/check_risky_artifacts.ps1")

    assert "providerTokenRegex" in src
    assert "github_pat_" in src
    assert "glpat-" in src
    assert "hf_" in src
    assert "npm_" in src
    assert "xox[baprs]-" in src
    assert "AKIA[0-9A-Z]{16}" in src
    assert "AIza[0-9A-Za-z_-]" in src
    assert "gsk_[A-Za-z0-9_]" in src
    assert "sk-ant-" in src
    assert "sk-or-v1-" in src
    assert "sk_car_" in src
    assert "sk-(proj|svcacct)-" in src
    assert "sk_(live|test)_" in src


def test_risky_artifact_check_blocks_real_lexa_license_keys():
    src = read("scripts/check_risky_artifacts.ps1")

    assert "lexaLicenseKeyRegex" in src
    assert "LEXA-(?!00000-00000-00000-00000" in src
    assert "[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}" in src
    assert "$text -match $lexaLicenseKeyRegex" in src


def test_risky_artifact_check_warn_mode_downgrades_blocking_findings():
    src = read("scripts/check_risky_artifacts.ps1")

    assert 'ValidateSet("Warn", "Strict")' in src
    assert '$Blocking -and $Mode -eq "Strict"' in src
    assert "$warnings.Add($Message)" in src
    assert "$resultLabel = \"passed\"" in src
    assert "$resultLabel = \"completed with warnings\"" in src


def test_risky_artifact_check_warns_nested_local_credentials_and_signing_material():
    src = read("scripts/check_risky_artifacts.ps1")

    for pathspec in [
        ":(glob)**/.npmrc",
        ":(glob)**/.aws/credentials",
        ":(glob)**/.docker/config.json",
        ":(glob)**/credentials.json",
        ":(glob)**/credentials.yaml",
        ":(glob)**/credentials.toml",
        ":(glob)**/secrets.json",
        ":(glob)**/secrets.yaml",
        ":(glob)**/secrets.toml",
        ":(glob)**/client_secret*.json",
        ":(glob)**/service-account*.json",
        ":(glob)**/service_account*.json",
        ":(glob)**/.ssh/id_rsa",
        ":(glob)**/pip.conf",
        ":(glob)**/*.pem",
        ":(glob)**/*.pfx",
        ":(glob)**/*.keystore",
    ]:
        assert pathspec in src


def test_risky_artifact_check_scans_staged_env_example_for_strong_secrets():
    src = read("scripts/check_risky_artifacts.ps1")

    assert "Test-StrongSecretLikeText" in src
    assert "Test-EnvExampleSecretLikeText" in src
    assert "Get-StagedOrWorkingTreeText" in src
    assert 'git show ":$normalized"' in src
    assert "envExampleSecretNameRegex" in src
    assert "envExamplePlaceholderValueRegex" in src
    assert "(?:export|set)\\s+" in src
    assert "\\$env:" in src
    assert "Secret-like value found in staged env placeholder file" in src
    assert "$normalizedFile -match '(^|/)\\.env\\.example$'" in src

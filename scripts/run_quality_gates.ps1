param(
  [ValidateSet("Quick", "Full", "Eval", "CI")]
  [string]$Mode = "Quick"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot "venv\Scripts\python.exe"
$Electron = Join-Path $RepoRoot "frontend\node_modules\electron\dist\electron.exe"
$PhaseGateTests = @(
  "tests/test_local_auth.py",
  "tests/test_companion_confirmation.py",
  "tests/test_router_companion.py",
  "tests/test_ai_engine.py",
  "tests/test_csp_static.py",
  "tests/test_hermes_adapter.py",
  "tests/test_os_agent_runtime.py",
  "tests/test_plugin_manager.py",
  "tests/test_plugin_permissions.py",
  "tests/test_eval_runner.py",
  "tests/test_eval_adapters.py",
  "tests/test_eval_tool_selection.py",
  "tests/test_eval_memory.py",
  "tests/test_eval_os_drafts.py",
  "tests/test_eval_security.py",
  "tests/test_agent_simulation.py",
  "tests/test_eval_agent_simulation.py",
  "tests/test_eval_trend_report.py",
  "tests/test_policy_dashboard.py",
  "tests/test_eval_baseline.py",
  "tests/test_eval_regression_checker.py",
  "tests/test_failure_triage.py",
  "tests/test_eval_baseline_update.py",
  "tests/test_release_candidate_check.py",
  "tests/test_backend_data_dir_static.py",
  "tests/test_build_backend_script.py",
  "tests/test_clean_temp_safety.py",
  "tests/test_remote_ci_readiness_script.py",
  "tests/test_codex_context_pack.py",
  "tests/test_quality_gate_scripts.py",
  "tests/test_dependency_repro_script.py",
  "tests/test_performance_budgets.py",
  "tests/test_risky_artifact_check.py",
  "tests/test_clean_clone_smoke_script.py",
  "tests/test_installer_smoke_script.py",
  "tests/test_packaged_smoke_script.py",
  "tests/test_packaging_config_static.py",
  "tests/test_start_launcher_static.py",
  "tests/test_fastapi_lifespan.py",
  "tests/test_eval_trace_replay.py",
  "tests/test_eval_plan_act_verify.py",
  "tests/test_eval_answer_quality.py",
  "tests/test_agent_protocol.py",
  "tests/test_agent_protocol_integration.py",
  "tests/test_agent_trace_capture.py",
  "tests/test_agent_trace_sampling.py",
  "tests/test_agent_policy_enforcement.py",
  "tests/test_synthetic_trace_generator.py",
  "tests/test_router_stripe_security.py"
)
$BackendCoverageTests = @(
  "tests/test_security.py",
  "tests/test_tool_registry_confirmation.py",
  "tests/test_local_auth.py",
  "tests/test_router_backup.py",
  "tests/test_router_rate_limits.py",
  "tests/test_main_v1_surface_static.py",
  "tests/test_router_stripe_security.py",
  "tests/test_backend_data_dir_static.py",
  "tests/test_context_bus.py",
  "tests/test_error_response.py",
  "tests/test_agent_trace_sampling.py",
  "tests/test_lexa_system_answer.py",
  "tests/test_workflow_templates.py"
)
$RiskyPaths = @(
  "personal_os",
  "tmp",
  "vendor",
  "audit.log",
  "bridge-audit.log",
  "lexa_memory.db",
  "lexa_memory.db-*",
  "hermes_workspace",
  "evals/results",
  "tmp/agent_traces",
  "dist",
  "dist-*-build",
  "backend-dist",
  "frontend/dist",
  "build",
  ".pytest_cache",
  ".coverage",
  "audio_cache",
  "node_modules",
  "frontend/node_modules",
  "venv",
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
  ":(glob)**/.netrc",
  ":(glob)**/.npmrc",
  ":(glob)**/.pnpmrc",
  ":(glob)**/.pypirc",
  ":(glob)**/.yarnrc",
  ":(glob)**/.yarnrc.yml",
  ":(glob)**/.aws/credentials",
  ":(glob)**/.aws/config",
  ":(glob)**/.azure/accessTokens.json",
  ":(glob)**/.azure/azureProfile.json",
  ":(glob)**/.config/gcloud/application_default_credentials.json",
  ":(glob)**/.docker/config.json",
  ":(glob)**/.gcloud/application_default_credentials.json",
  ":(glob)**/.kube/config",
  ":(glob)**/credentials.json",
  ":(glob)**/credentials.yml",
  ":(glob)**/credentials.yaml",
  ":(glob)**/credentials.toml",
  ":(glob)**/credentials.ini",
  ":(glob)**/credentials.conf",
  ":(glob)**/secrets.json",
  ":(glob)**/secrets.yml",
  ":(glob)**/secrets.yaml",
  ":(glob)**/secrets.toml",
  ":(glob)**/secrets.ini",
  ":(glob)**/secrets.conf",
  ":(glob)**/client_secret*.json",
  ":(glob)**/service-account*.json",
  ":(glob)**/service_account*.json",
  ":(glob)**/.ssh/id_dsa",
  ":(glob)**/.ssh/id_ecdsa",
  ":(glob)**/.ssh/id_ed25519",
  ":(glob)**/.ssh/id_rsa",
  ":(glob)**/id_dsa",
  ":(glob)**/id_ecdsa",
  ":(glob)**/id_ed25519",
  ":(glob)**/id_rsa",
  ":(glob)**/pip.conf",
  ":(glob)**/pip.ini",
  ":(glob)**/*.pfx",
  ":(glob)**/*.p12",
  ":(glob)**/*.pem",
  ":(glob)**/*.ppk",
  ":(glob)**/*.key",
  ":(glob)**/*.pvk",
  ":(glob)**/*.cer",
  ":(glob)**/*.crt",
  ":(glob)**/*.spc",
  ":(glob)**/*.jks",
  ":(glob)**/*.keystore"
)
$RiskyStagedPattern = '^(?!(.*/)?\.env\.example$)(personal_os/|tmp/|vendor/|audit\.log$|bridge-audit\.log$|lexa_memory\.db|hermes_workspace/|evals/results/|tmp/agent_traces/|dist/|dist-[^/]*build/|backend-dist/|frontend/dist/|build/|\.pytest_cache/|\.coverage$|audio_cache/|(.*/)?node_modules/|venv/|(.*/)?\.env($|\.|/)|.*\.env$|(.*/)?\.netrc$|(.*/)?\.(npmrc|pnpmrc|pypirc)$|(.*/)?\.yarnrc(\.yml)?$|(.*/)?\.aws/(credentials|config)$|(.*/)?\.azure/(accessTokens|azureProfile)\.json$|(.*/)?\.config/gcloud/application_default_credentials\.json$|(.*/)?\.docker/config\.json$|(.*/)?\.gcloud/application_default_credentials\.json$|(.*/)?\.kube/config$|(.*/)?(credentials|secrets)\.(json|ya?ml|toml|ini|conf)$|(.*/)?client_secret[^/]*\.json$|(.*/)?service[-_]?account[^/]*\.json$|(.*/)?\.ssh/(id_dsa|id_ecdsa|id_ed25519|id_rsa)$|(.*/)?(id_dsa|id_ecdsa|id_ed25519|id_rsa)$|(.*/)?pip\.(conf|ini)$|.*\.(pfx|p12|pem|ppk|key|pvk|cer|crt|spc|jks|keystore)$|(.*/)?(codesign|code-sign|signing|signtool)[^/]*\.(json|ps1|env|txt|xml)$|(.*/)?(windows|electron)[_-]?(signing|certificate|cert)[^/]*\.(json|ps1|env|txt|xml)$)'

function Invoke-Gate {
  param(
    [string]$Name,
    [scriptblock]$Command
  )
  Write-Host ""
  Write-Host "== $Name =="
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE"
  }
}

function Invoke-GitSafety {
  if (!(Test-Path -LiteralPath (Join-Path $RepoRoot ".git"))) {
    Write-Warning "No .git directory found; git diff/staged safety checks are skipped for this source-only clean install workspace."
    return
  }
  Invoke-Gate "git diff --check" { git -c core.autocrlf=false diff --check }

  Write-Host ""
  Write-Host "== git risky-path scan =="
  $statusArgs = @("status", "--short", "--") + $RiskyPaths
  $riskStatus = & git @statusArgs
  if ($riskStatus) {
    Write-Warning "Risky local paths are present. Do not stage or commit these unless explicitly reviewed."
    $riskStatus | ForEach-Object { Write-Warning $_ }
  } else {
    Write-Host "No risky local paths reported by git status."
  }

  $staged = & git diff --cached --name-only
  $riskyStaged = @($staged | Where-Object { $_ -match $RiskyStagedPattern })
  if ($riskyStaged.Count -gt 0) {
    throw "Risky paths are staged: $($riskyStaged -join ', ')"
  }
  Write-Host "No risky paths are staged."
}

function Invoke-RiskyArtifactCheck {
  Invoke-Gate "risky artifact check" { powershell -ExecutionPolicy Bypass -File "scripts\check_risky_artifacts.ps1" -Mode Strict }
}

function Invoke-PythonPhaseGate {
  if (!(Test-Path $Python)) {
    throw "Python venv not found at $Python"
  }
  Invoke-Gate "python phase gate" { & $Python -m pytest -q @PhaseGateTests }
}

function Invoke-BackendCoverageSmoke {
  if (!(Test-Path $Python)) {
    throw "Python venv not found at $Python"
  }
  Invoke-Gate "backend coverage smoke" {
    & $Python -m pytest -q --cov=backend --cov-report=term-missing:skip-covered @BackendCoverageTests
  }
}

function Invoke-FullPython {
  if (!(Test-Path $Python)) {
    throw "Python venv not found at $Python"
  }
  Invoke-Gate "full python tests" { & $Python -m pytest -q }
}

function Invoke-EvalSuite {
  if (!(Test-Path $Python)) {
    throw "Python venv not found at $Python"
  }
  Invoke-Gate "offline eval suite" { & $Python "evals\runners\run_eval_suite.py" --all }
}

function Invoke-EvalRegressionGate {
  Invoke-Gate "eval regression gate" { powershell -ExecutionPolicy Bypass -File "scripts\run_eval_regression_gate.ps1" }
}

function Invoke-DependencyReproCheck {
  Invoke-Gate "dependency reproducibility check" { powershell -ExecutionPolicy Bypass -File "scripts\check_dependency_repro.ps1" }
}

function Invoke-PackagingConfigSmoke {
  Invoke-Gate "packaging config smoke" { powershell -ExecutionPolicy Bypass -File "scripts\run_packaging_smoke.ps1" }
}

function Invoke-JsStaticGate {
  $tests = Get-ChildItem (Join-Path $RepoRoot "tests") -Filter "test_*.js" | Sort-Object Name
  if ($tests.Count -eq 0) {
    Write-Warning "No JS static tests found."
    return
  }
  foreach ($test in $tests) {
    Invoke-Gate "node $($test.Name)" { node $test.FullName }
  }
  Write-Host ""
  Write-Host "JS static gate completed: $($tests.Count) files."
}

function Invoke-VendorAssetCheck {
  Invoke-Gate "bundled vendor asset check" { node "frontend\scripts\sync-vendor.cjs" --check }
}

function Invoke-ElectronSmokeGate {
  if (!(Test-Path $Electron)) {
    Write-Warning "Electron binary not found at $Electron; skipping Electron smoke gate."
    return
  }
  Invoke-Gate "electron startup health smoke" { & $Electron "tests/electron_startup_health_smoke.js" }
  Invoke-Gate "electron presence challenge smoke" { & $Electron "tests/electron_presence_challenge_smoke.js" }
  Invoke-Gate "electron UI visual smoke" { & $Electron "tests/electron_ui_visual_smoke.js" }
}

Write-Host "Lexa quality gates ($Mode)"
Invoke-GitSafety
Invoke-RiskyArtifactCheck

if ($Mode -eq "Eval") {
  Invoke-EvalSuite
  Invoke-EvalRegressionGate
  Write-Host ""
  Write-Host "Quality gates passed ($Mode)."
  exit 0
}

Invoke-PythonPhaseGate
Invoke-BackendCoverageSmoke
Invoke-EvalSuite
Invoke-VendorAssetCheck
Invoke-JsStaticGate

if ($Mode -eq "CI") {
  Invoke-EvalRegressionGate
  Invoke-PackagingConfigSmoke
  Invoke-DependencyReproCheck
  Write-Host ""
  Write-Host "Quality gates passed ($Mode)."
  exit 0
}

if ($Mode -eq "Full") {
  Invoke-EvalRegressionGate
  Invoke-FullPython
  Invoke-ElectronSmokeGate
}

Write-Host ""
Write-Host "Quality gates passed ($Mode)."

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
  "tests/test_quality_gate_scripts.py",
  "tests/test_performance_budgets.py",
  "tests/test_risky_artifact_check.py",
  "tests/test_clean_clone_smoke_script.py",
  "tests/test_installer_smoke_script.py",
  "tests/test_fastapi_lifespan.py",
  "tests/test_eval_trace_replay.py",
  "tests/test_eval_plan_act_verify.py",
  "tests/test_eval_answer_quality.py",
  "tests/test_agent_protocol.py",
  "tests/test_agent_protocol_integration.py",
  "tests/test_agent_trace_capture.py",
  "tests/test_agent_trace_sampling.py",
  "tests/test_agent_policy_enforcement.py",
  "tests/test_synthetic_trace_generator.py"
)
$RiskyPaths = @(
  "personal_os",
  "tmp",
  "vendor",
  "audit.log",
  "bridge-audit.log",
  "lexa_memory.db",
  "lexa_memory.db-*",
  "hermes_workspace"
)
$RiskyStagedPattern = "^(personal_os/|tmp/|vendor/|audit\.log$|bridge-audit\.log$|lexa_memory\.db|hermes_workspace/)"

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
Invoke-EvalSuite
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

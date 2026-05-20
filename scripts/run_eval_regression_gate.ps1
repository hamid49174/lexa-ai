param(
  [string]$Baseline = "evals\baselines\eval_baseline.json",
  [string]$WorkDir = "",
  [switch]$PersistFailureReport
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot "venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
  throw "Python venv not found at $Python"
}

if ($WorkDir) {
  $GateDir = $WorkDir
} else {
  $GateDir = Join-Path $RepoRoot (Join-Path ".test-tmp" ("eval-regression-" + [guid]::NewGuid().ToString("N")))
}
New-Item -ItemType Directory -Force $GateDir | Out-Null

$CurrentReport = Join-Path $GateDir "current_eval_report.json"
$RegressionReport = Join-Path $GateDir "eval_regression_report.json"
$TriageReport = Join-Path $GateDir "failure_triage.md"
if ($PersistFailureReport) {
  $TriageReport = Join-Path $RepoRoot "evals\results\eval_regression_triage.md"
}

Write-Host "== offline eval suite =="
& $Python "evals\runners\run_eval_suite.py" --all --json-report $CurrentReport
if ($LASTEXITCODE -ne 0) {
  throw "offline eval suite failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "== eval regression check =="
& $Python "evals\runners\check_eval_regressions.py" --baseline $Baseline --current $CurrentReport --output-json $RegressionReport --triage-md $TriageReport
if ($LASTEXITCODE -ne 0) {
  Write-Error "Eval regression gate failed. Triage report: $TriageReport"
  exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Eval regression gate passed."

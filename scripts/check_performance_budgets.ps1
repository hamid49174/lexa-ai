param(
  [string]$RepoRoot = "",
  [int]$EvalSuiteWarnSeconds = 30,
  [switch]$Strict
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
} else {
  $RepoRoot = Resolve-Path -LiteralPath $RepoRoot
}

# Prefer the project venv; fall back to LEXA_PYTHON or the python on PATH (CI runners).
$python = Join-Path $RepoRoot "venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $python)) {
  if ($env:LEXA_PYTHON -and (Test-Path -LiteralPath $env:LEXA_PYTHON)) {
    $python = $env:LEXA_PYTHON
  } else {
    $pathPython = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pathPython) { throw "Python not found: no venv at $RepoRoot\venv, no LEXA_PYTHON, no python on PATH" }
    $python = $pathPython.Source
  }
}

Write-Host "Performance budget smoke"
Write-Host "Budgets are warn-only by default. Use -Strict to fail on overruns."

$elapsed = Measure-Command {
  & $python "evals\runners\run_eval_suite.py" --all
  if ($LASTEXITCODE -ne 0) { throw "Eval suite failed during performance budget smoke." }
}

$seconds = [Math]::Round($elapsed.TotalSeconds, 2)
Write-Host "Eval suite duration: ${seconds}s (warn target: ${EvalSuiteWarnSeconds}s)"
if ($seconds -gt $EvalSuiteWarnSeconds) {
  $message = "Eval suite exceeded warn target: ${seconds}s > ${EvalSuiteWarnSeconds}s"
  if ($Strict) { throw $message }
  Write-Warning $message
}

Write-Host "Performance budget smoke completed."
exit 0

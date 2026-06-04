param(
  [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
} else {
  $RepoRoot = Resolve-Path -LiteralPath $RepoRoot
}

$python = Join-Path $RepoRoot "venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $python)) { throw "Python venv not found at $python" }

Write-Host "Hermes adapter safety smoke"
& $python -m pytest -q tests/test_hermes_adapter.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$hermesWorkspace = Join-Path $RepoRoot "hermes_workspace"
if (Test-Path -LiteralPath (Join-Path $hermesWorkspace ".env")) {
  Write-Warning "hermes_workspace/.env exists locally. It must remain ignored and unstaged."
}
if (Test-Path -LiteralPath $hermesWorkspace) {
  & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "check_risky_artifacts.ps1") -Root $hermesWorkspace -Mode Warn -ArtifactPath $hermesWorkspace
  if ($LASTEXITCODE -ne 0) {
    throw "Hermes workspace risky artifact check failed with exit code $LASTEXITCODE"
  }
}

$staged = @(git -C $RepoRoot diff --cached --name-only -- hermes_workspace vendor/hermes-agent 2>$null)
if ($staged.Count -gt 0) {
  throw "Hermes workspace/vendor paths are staged: $($staged -join ', ')"
}

Write-Host "Hermes smoke completed without external Telegram/API calls."
exit 0

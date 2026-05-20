param(
  [switch]$SkipFullQualityGate,
  [switch]$RunPackagingBuild,
  [switch]$AllowMissingOS,
  [switch]$AllowMissingWebsite
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

function Invoke-RcStep {
  param(
    [string]$Name,
    [scriptblock]$Command,
    [bool]$Optional = $false
  )
  Write-Host ""
  Write-Host "== $Name =="
  try {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
  } catch {
    if ($Optional) {
      Write-Warning "$Name skipped/failed as optional: $($_.Exception.Message)"
      return
    }
    throw
  }
}

Write-Host "Lexa Release Candidate Check"
Write-Host "RepoRoot: $RepoRoot"
Write-Host "No release action, deletion, or artifact staging is performed by this script."

if (-not $SkipFullQualityGate) {
  Invoke-RcStep "Quality Gates Full" { powershell -ExecutionPolicy Bypass -File "scripts\run_quality_gates.ps1" -Mode Full }
}

Invoke-RcStep "Eval Regression Gate" { powershell -ExecutionPolicy Bypass -File "scripts\run_eval_regression_gate.ps1" }
Invoke-RcStep "Risky Artifact Check" { powershell -ExecutionPolicy Bypass -File "scripts\check_risky_artifacts.ps1" -Mode Strict }
Invoke-RcStep "Electron Startup Health Smoke" { node "tests\electron_startup_health_smoke.js" }
Invoke-RcStep "Electron Presence Smoke" { node "tests\electron_presence_challenge_smoke.js" }
Invoke-RcStep "OS Quality Gates" {
  if ($AllowMissingOS) {
    powershell -ExecutionPolicy Bypass -File "scripts\run_os_quality_gates.ps1" -AllowMissing
  } else {
    powershell -ExecutionPolicy Bypass -File "scripts\run_os_quality_gates.ps1"
  }
} $AllowMissingOS
Invoke-RcStep "Hermes Smoke" { powershell -ExecutionPolicy Bypass -File "scripts\run_hermes_smoke.ps1" }
Invoke-RcStep "Website Smoke" { powershell -ExecutionPolicy Bypass -File "scripts\run_website_smoke.ps1" } $AllowMissingWebsite
Invoke-RcStep "Packaging Smoke" {
  if ($RunPackagingBuild) {
    powershell -ExecutionPolicy Bypass -File "scripts\run_packaging_smoke.ps1" -Build
  } else {
    powershell -ExecutionPolicy Bypass -File "scripts\run_packaging_smoke.ps1"
  }
}
Invoke-RcStep "Performance Budget Smoke" { powershell -ExecutionPolicy Bypass -File "scripts\check_performance_budgets.ps1" }
Invoke-RcStep "Git Safety" {
  git -c core.autocrlf=false diff --check
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  $staged = @(git diff --cached --name-only)
  if ($staged.Count -gt 0) {
    Write-Warning "Files are staged during RC check: $($staged -join ', ')"
  }
}

Write-Host ""
Write-Host "Release Candidate Check passed."
exit 0

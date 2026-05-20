param(
  [ValidateSet("LocalFull", "CICore", "Packaging", "Installer", "StrictRC")]
  [string]$Mode = "LocalFull",
  [switch]$SkipFullQualityGate,
  [switch]$RunPackagingBuild,
  [switch]$AllowMissingOS,
  [switch]$AllowMissingWebsite
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
$Script:RcWarnings = New-Object System.Collections.Generic.List[string]

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
      $message = "$Name skipped/failed as optional: $($_.Exception.Message)"
      Write-Warning $message
      $Script:RcWarnings.Add($message) | Out-Null
      return
    }
    throw
  }
}

function Add-RcWarning {
  param([string]$Message)
  Write-Warning $Message
  $Script:RcWarnings.Add($Message) | Out-Null
}

function Complete-RcCheck {
  param([string]$ModeName)
  $decision = if ($Script:RcWarnings.Count -gt 0) { "Needs Review" } else { "Ready" }
  Write-Host ""
  Write-Host "Release decision: $decision"
  if ($Script:RcWarnings.Count -gt 0) {
    Write-Host "Warnings:"
    $Script:RcWarnings | ForEach-Object { Write-Host "- $_" }
  }
  Write-Host "Release Candidate Check passed ($ModeName)."
}

Write-Host "Lexa Release Candidate Check"
Write-Host "RepoRoot: $RepoRoot"
Write-Host "Mode: $Mode"
Write-Host "No release action, deletion, or artifact staging is performed by this script."

$buildForMode = $RunPackagingBuild -or $Mode -in @("Packaging", "StrictRC")
$packagingArtifactRoot = if ($buildForMode) {
  Join-Path ([System.IO.Path]::GetTempPath()) ("lexa-rc-packaging-" + [guid]::NewGuid().ToString("N"))
} else {
  ""
}

if ($Mode -eq "CICore") {
  Invoke-RcStep "Quality Gates CI" { powershell -ExecutionPolicy Bypass -File "scripts\run_quality_gates.ps1" -Mode CI }
  Invoke-RcStep "Eval Regression Gate" { powershell -ExecutionPolicy Bypass -File "scripts\run_eval_regression_gate.ps1" }
  Invoke-RcStep "Risky Artifact Check" { powershell -ExecutionPolicy Bypass -File "scripts\check_risky_artifacts.ps1" -Mode Strict }
  Invoke-RcStep "Dependency Repro Check" { powershell -ExecutionPolicy Bypass -File "scripts\check_dependency_repro.ps1" }
  Invoke-RcStep "Packaging Config Smoke" { powershell -ExecutionPolicy Bypass -File "scripts\run_packaging_smoke.ps1" }
  Invoke-RcStep "OS Quality Gates Optional" { powershell -ExecutionPolicy Bypass -File "scripts\run_os_quality_gates.ps1" -AllowMissing } $true
  Invoke-RcStep "Website Smoke Optional" { powershell -ExecutionPolicy Bypass -File "scripts\run_website_smoke.ps1" } $true
  Invoke-RcStep "Git Safety" { git -c core.autocrlf=false diff --check }
  Add-RcWarning "Remote GitHub Actions run is not proven by CICore. This mode proves local CI-equivalent checks only."
  Complete-RcCheck $Mode
  exit 0
}

if ($Mode -eq "Packaging") {
  Write-Host "Packaging mode runs dependency, artifact, packaging-build, installer, performance, and git checks only."
}

if ($Mode -eq "Installer") {
  Write-Host "Installer mode validates an existing installer artifact and documents unsigned/not-yet-installed status."
}

if (-not $SkipFullQualityGate -and $Mode -notin @("Packaging", "Installer")) {
  Invoke-RcStep "Quality Gates Full" { powershell -ExecutionPolicy Bypass -File "scripts\run_quality_gates.ps1" -Mode Full }
}

if ($Mode -ne "Installer") {
  Invoke-RcStep "Clean Clone Smoke" { powershell -ExecutionPolicy Bypass -File "scripts\run_clean_clone_smoke.ps1" }
  Invoke-RcStep "Dependency Repro Check" { powershell -ExecutionPolicy Bypass -File "scripts\check_dependency_repro.ps1" }
  Invoke-RcStep "Eval Regression Gate" { powershell -ExecutionPolicy Bypass -File "scripts\run_eval_regression_gate.ps1" }
  Invoke-RcStep "Risky Artifact Check" { powershell -ExecutionPolicy Bypass -File "scripts\check_risky_artifacts.ps1" -Mode Strict }
} else {
  Invoke-RcStep "Risky Artifact Check" { powershell -ExecutionPolicy Bypass -File "scripts\check_risky_artifacts.ps1" -Mode Strict }
}

if ($Mode -notin @("Packaging", "Installer")) {
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
}

Invoke-RcStep "Packaging Smoke" {
  if ($Mode -eq "Installer") {
    powershell -ExecutionPolicy Bypass -File "scripts\run_packaging_smoke.ps1"
  } elseif ($buildForMode) {
    powershell -ExecutionPolicy Bypass -File "scripts\run_packaging_smoke.ps1" -Build -ArtifactRoot $packagingArtifactRoot
  } else {
    powershell -ExecutionPolicy Bypass -File "scripts\run_packaging_smoke.ps1"
  }
}
Invoke-RcStep "Installer Smoke" {
  if ($buildForMode) {
    powershell -ExecutionPolicy Bypass -File "scripts\run_installer_smoke.ps1" -ArtifactRoot $packagingArtifactRoot -RequireInstaller
  } elseif ($Mode -eq "Installer") {
    powershell -ExecutionPolicy Bypass -File "scripts\run_installer_smoke.ps1" -RequireInstaller
  } else {
    powershell -ExecutionPolicy Bypass -File "scripts\run_installer_smoke.ps1"
  }
} ($Mode -ne "StrictRC" -and -not $buildForMode)

if ($Mode -in @("Installer", "StrictRC")) {
  Add-RcWarning "Installer install/uninstall in a disposable VM is not proven by this local script unless run_installer_smoke.ps1 is executed with an approved VM-only procedure."
}
if ($Mode -eq "StrictRC") {
  Add-RcWarning "Unsigned installer is a release review item until Windows code signing is configured."
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
Complete-RcCheck $Mode
exit 0

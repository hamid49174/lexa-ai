param(
  [ValidateSet("LocalFull", "CICore", "Packaging", "Installer", "StrictRC")]
  [string]$Mode = "LocalFull",
  [ValidateSet("InternalRC", "PublicRC", "PublicRelease")]
  [string]$Target = "InternalRC",
  [switch]$SkipFullQualityGate,
  [switch]$RunPackagingBuild,
  [switch]$AllowMissingOS,
  [switch]$AllowMissingWebsite
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
$Script:RcWarnings = New-Object System.Collections.Generic.List[string]
$Script:RcBlockers = New-Object System.Collections.Generic.List[string]
$Script:RcFacts = @{}

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

function Add-RcBlocker {
  param([string]$Message)
  $Script:RcBlockers.Add($Message) | Out-Null
}

function Add-TargetFinding {
  param(
    [string]$Message,
    [string[]]$BlockingTargets = @()
  )
  if ($Target -in $BlockingTargets) {
    Add-RcBlocker $Message
  } else {
    Add-RcWarning $Message
  }
}

function Test-GithubRemoteConfigured {
  $remotes = @(git remote -v 2>$null)
  foreach ($remote in $remotes) {
    if ($remote -match 'github\.com[:/]' -or $remote -match 'https://github\.com/') {
      return $true
    }
  }
  return $false
}

function Get-InstallerSigningStatus {
  param([string]$ArtifactRoot)
  if (-not $ArtifactRoot -or !(Test-Path -LiteralPath $ArtifactRoot)) {
    return "not-found"
  }
  $installer = Get-ChildItem -LiteralPath $ArtifactRoot -Recurse -Force -File -Include "*.exe", "*.msi", "*.msix" -ErrorAction SilentlyContinue |
    Sort-Object Length -Descending |
    Select-Object -First 1
  if (-not $installer) { return "not-found" }
  try {
    $signature = Get-AuthenticodeSignature -LiteralPath $installer.FullName -ErrorAction Stop
    if ($signature.Status -eq "Valid") { return "signed" }
    if ($signature.Status -eq "NotSigned") { return "unsigned" }
    return "unknown:$($signature.Status)"
  } catch {
    return "unknown"
  }
}

function Complete-RcCheck {
  param([string]$ModeName, [string]$TargetName)
  $decision = if ($Script:RcBlockers.Count -gt 0) { "Blocked" } elseif ($Script:RcWarnings.Count -gt 0) { "Needs Review" } else { "Ready" }
  Write-Host ""
  Write-Host "Release decision: $decision"
  Write-Host "Release target: $TargetName"
  if ($Script:RcBlockers.Count -gt 0) {
    Write-Host "Blocking findings:"
    $Script:RcBlockers | ForEach-Object { Write-Host "- $_" }
  }
  if ($Script:RcWarnings.Count -gt 0) {
    Write-Host "Warnings:"
    $Script:RcWarnings | ForEach-Object { Write-Host "- $_" }
  }
  if ($Script:RcBlockers.Count -gt 0) {
    Write-Host "Release Candidate Check blocked ($ModeName / $TargetName)."
    exit 1
  }
  Write-Host "Release Candidate Check passed ($ModeName / $TargetName)."
}

Write-Host "Lexa Release Candidate Check"
Write-Host "RepoRoot: $RepoRoot"
Write-Host "Mode: $Mode"
Write-Host "Target: $Target"
Write-Host "No release action, deletion, or artifact staging is performed by this script."

if (Test-GithubRemoteConfigured) {
  $Script:RcFacts["github_remote"] = $true
} else {
  $Script:RcFacts["github_remote"] = $false
}

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
  Add-TargetFinding "Remote GitHub Actions run is not proven by CICore. This mode proves local CI-equivalent checks only." @("PublicRC", "PublicRelease")
  Complete-RcCheck $Mode $Target
  exit 0
}

if ($Mode -eq "Packaging") {
  Write-Host "Packaging mode runs dependency, artifact, packaging-build, installer, performance, and git checks only."
}

if ($Mode -eq "Installer") {
  Write-Host "Installer mode validates an existing installer artifact and documents unsigned/not-yet-installed status."
}

if (-not $Script:RcFacts["github_remote"]) {
  Add-TargetFinding "Remote CI is not yet remotely proven because no GitHub remote is configured." @("PublicRC", "PublicRelease")
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

if ($Mode -in @("Installer", "StrictRC") -or $Target -in @("PublicRC", "PublicRelease")) {
  Add-TargetFinding "Installer install/uninstall in a disposable VM is not proven by this local script unless run_installer_smoke.ps1 is executed with an approved VM-only procedure." @("PublicRC", "PublicRelease")
}
$installerSigningRoot = if ($buildForMode) { $packagingArtifactRoot } else { Join-Path $RepoRoot "dist" }
$installerSigningStatus = Get-InstallerSigningStatus $installerSigningRoot
Write-Host "Installer signing gate status: $installerSigningStatus"
if ($installerSigningStatus -ne "signed") {
  Add-TargetFinding "Installer signing status is '$installerSigningStatus'. Unsigned or unknown installers are warn-only for InternalRC and block PublicRC/PublicRelease." @("PublicRC", "PublicRelease")
}
if ($Target -in @("PublicRC", "PublicRelease")) {
  Add-RcBlocker "Website release target is still static/external without package-based build/lint proof."
  Add-RcBlocker "OS cleanup remains unreviewed in a separate dirty OS repository."
}
if ($Target -eq "PublicRelease") {
  Add-RcBlocker "PublicRelease requires signed installer, proven VM install/uninstall, remote CI proof, and website release workflow."
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
Complete-RcCheck $Mode $Target
exit 0

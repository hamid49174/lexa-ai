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
$Script:RcNextActions = New-Object System.Collections.Generic.List[string]
$Script:RcExternalPrerequisites = New-Object System.Collections.Generic.List[string]
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

function Add-UniqueListItem {
  param(
    [System.Collections.Generic.List[string]]$List,
    [string]$Message
  )
  if ($Message -and -not $List.Contains($Message)) {
    $List.Add($Message) | Out-Null
  }
}

function Add-RcNextAction {
  param([string]$Message)
  Add-UniqueListItem $Script:RcNextActions $Message
}

function Add-RcExternalPrerequisite {
  param([string]$Message)
  Add-UniqueListItem $Script:RcExternalPrerequisites $Message
}

function Invoke-PaidLicenseSmokeForTarget {
  $hasSmokeKey = -not [string]::IsNullOrWhiteSpace($env:LEXA_LICENSE_SMOKE_KEY)
  if ($hasSmokeKey) {
    Invoke-RcStep "Paid License Smoke" { powershell -ExecutionPolicy Bypass -File "scripts\run_paid_license_smoke.ps1" }
    $Script:RcFacts["paid_license_smoke"] = $true
    return
  }

  $Script:RcFacts["paid_license_smoke"] = $false
  if ($Target -eq "InternalRC") {
    Add-RcWarning "[License] Paid activation smoke is not proven because LEXA_LICENSE_SMOKE_KEY is not set."
  }
  Add-RcNextAction "Set LEXA_LICENSE_SMOKE_KEY, LEXA_LICENSE_SMOKE_API_URL, and optional LEXA_LICENSE_SMOKE_EXPECTED_PLAN outside Git; run scripts\run_paid_license_smoke.ps1 before PublicRC."
  Add-RcExternalPrerequisite "Real Supabase/Stripe subscription and a valid paid Lexa license key."
}

function Test-WebsitePublicConfigResolved {
  $websiteRootInfo = Resolve-Path -LiteralPath (Join-Path $RepoRoot "..\lexa-website") -ErrorAction SilentlyContinue
  if (-not $websiteRootInfo) { return $false }

  $runtimeConfig = Join-Path $websiteRootInfo.Path "config.runtime.js"
  if (!(Test-Path -LiteralPath $runtimeConfig)) { return $false }

  $runtimeText = Get-Content -LiteralPath $runtimeConfig -Raw
  if ($runtimeText -notmatch 'window\.LEXA_CONFIG') { return $false }
  if ($runtimeText -match 'YOUR_PROJECT|YOUR_ANON_KEY|YOUR_KEY|YOUR_PORTAL_ID|price_(PRO|ULTRA)_[A-Z_]*ID|pk_(live|test)_YOUR') {
    return $false
  }
  $requiredConfig = @(
    @{ Key = "SUPABASE_URL"; Pattern = '^https://[a-z0-9-]+\.supabase\.co/?$' },
    @{ Key = "SUPABASE_ANON_KEY"; Pattern = '^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$' },
    @{ Key = "STRIPE_PUBLISHABLE_KEY"; Pattern = '^pk_(live|test)_[A-Za-z0-9_=-]{10,}$' },
    @{ Key = "APP_URL"; Pattern = '^https://[^/\s]+' },
    @{ Key = "API_URL"; Pattern = '^https://[^/\s]+' },
    @{ Key = "pro_monthly"; Pattern = '^price_[A-Za-z0-9_]{8,}$' },
    @{ Key = "pro_yearly"; Pattern = '^price_[A-Za-z0-9_]{8,}$' },
    @{ Key = "ultra_monthly"; Pattern = '^price_[A-Za-z0-9_]{8,}$' },
    @{ Key = "ultra_yearly"; Pattern = '^price_[A-Za-z0-9_]{8,}$' }
  )
  foreach ($item in $requiredConfig) {
    $escapedKey = [regex]::Escape($item.Key)
    $match = [regex]::Match($runtimeText, "$escapedKey\s*:\s*['""]([^'""]+)['""]")
    if (-not $match.Success -or $match.Groups[1].Value.Trim() -notmatch $item.Pattern) {
      return $false
    }
  }
  return $true
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
  if ($Script:RcNextActions.Count -gt 0) {
    Write-Host "Next actions:"
    $Script:RcNextActions | ForEach-Object { Write-Host "- $_" }
  }
  if ($Script:RcExternalPrerequisites.Count -gt 0) {
    Write-Host "External prerequisites:"
    $Script:RcExternalPrerequisites | ForEach-Object { Write-Host "- $_" }
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

Invoke-RcStep "Remote CI Readiness" { powershell -ExecutionPolicy Bypass -File "scripts\check_remote_ci_readiness.ps1" }

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
  Add-TargetFinding "[CI] Remote CI is not yet remotely proven because no GitHub remote is configured." @("PublicRC", "PublicRelease")
  Add-RcNextAction "Create a GitHub remote, push the branch, run the quality-gates workflow, and record the run URL plus commit SHA."
  Add-RcExternalPrerequisite "GitHub repository with Actions enabled."
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
  $Script:RcFacts["website_public_config"] = Test-WebsitePublicConfigResolved
  Invoke-PaidLicenseSmokeForTarget
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
  Add-TargetFinding "[Installer] Installer install/uninstall in a disposable VM is not proven by this local script unless run_installer_smoke.ps1 is executed with an approved VM-only procedure." @("PublicRC", "PublicRelease")
  Add-RcNextAction "Run installer install/uninstall proof in a disposable VM or Windows Sandbox with -VMOnly."
  Add-RcExternalPrerequisite "Disposable Windows VM or Windows Sandbox."
}
$installerSigningRoot = if ($buildForMode) { $packagingArtifactRoot } else { Join-Path $RepoRoot "dist" }
$installerSigningStatus = Get-InstallerSigningStatus $installerSigningRoot
Write-Host "Installer signing gate status: $installerSigningStatus"
if ($installerSigningStatus -ne "signed") {
  Add-TargetFinding "[Signing] Installer signing status is '$installerSigningStatus'. Unsigned or unknown installers are warn-only for InternalRC and block PublicRC/PublicRelease." @("PublicRC", "PublicRelease")
  Add-RcNextAction "Configure Windows signing outside Git, rebuild, and verify the expected signer identity."
  Add-RcExternalPrerequisite "Windows code signing certificate and protected secret store."
}
if ($Target -in @("PublicRC", "PublicRelease")) {
  if (-not $Script:RcFacts.ContainsKey("website_public_config") -or -not $Script:RcFacts["website_public_config"]) {
    Add-RcBlocker "[Website] Public Supabase/Stripe config placeholders remain unresolved outside Git."
    Add-RcNextAction "Set public Supabase URL, Supabase anon key, Stripe client key, and allowed Stripe price IDs outside Git."
  }
  Add-RcBlocker "[Website] Stripe.js allowlist/CSP policy needs release-owner approval for PublicRC/PublicRelease."
  if (-not $Script:RcFacts.ContainsKey("paid_license_smoke") -or -not $Script:RcFacts["paid_license_smoke"]) {
    Add-RcBlocker "[License] Paid activation smoke with real Supabase/Stripe config is not proven by scripts\run_paid_license_smoke.ps1."
  }
  Add-RcBlocker "[OS] OS cleanup remains unreviewed in a separate dirty OS repository."
  Add-RcBlocker "[Release] Public artifact policy is not proven on remote CI."
  Add-RcNextAction "Approve the website Stripe.js external-script/CSP policy before PublicRC; Supabase is vendored and linted locally."
  Add-RcNextAction "Run scripts\run_paid_license_smoke.ps1 against real Supabase/Stripe config and record the entitlement-policy decision."
  Add-RcNextAction "Run the OS cleanup review as a separate backup-first OS project."
  Add-RcNextAction "Prove risky artifact and result-path policy on GitHub Actions before PublicRC."
  Add-RcExternalPrerequisite "Public website configuration values and release-owner CSP approval."
  Add-RcExternalPrerequisite "Real Supabase/Stripe environment for paid activation proof."
  Add-RcExternalPrerequisite "Human review of the external OS dirty state."
  Add-RcExternalPrerequisite "Remote CI proof for public artifact policy."
}
if ($Target -eq "PublicRC") {
  Add-RcWarning "[Privacy] Privacy/trace consent checklist should be reviewed before broad PublicRC testing and remains blocking for PublicRelease."
}
if ($Target -eq "PublicRelease") {
  $privacyChecklist = Join-Path $RepoRoot "docs\release\privacy_trace_consent_checklist.md"
  if (Test-Path -LiteralPath $privacyChecklist) {
    Add-RcBlocker "[Privacy] Public release privacy and trace consent checklist exists but is not finalized or approved."
  } else {
    Add-RcBlocker "[Privacy] Public release privacy and trace consent checklist is missing."
  }
  Add-RcBlocker "[Release] PublicRelease requires signed installer, proven VM install/uninstall, remote CI proof, and website release workflow."
  Add-RcNextAction "Review docs\release\privacy_trace_consent_checklist.md and record release-owner approval before public release."
  Add-RcExternalPrerequisite "Release-owner privacy and trace-consent approval."
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

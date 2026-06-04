param(
  [string]$OSRoot = "",
  [switch]$AllowMissing
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")

$ExpectedOsSubdirs = @(
  "00_System\SDK\os-sdk",
  "11_Integrations\MCP\os-mcp-server",
  "07_Automations\Workflows\raw-inbox-worker"
)

function Test-ExistingDirectory {
  param([string]$Path)
  if (-not $Path) { return $false }
  try {
    return (Test-Path -LiteralPath $Path -PathType Container)
  } catch {
    return $false
  }
}

function Add-OSRootCandidate {
  param(
    [System.Collections.Generic.List[string]]$Candidates,
    [string]$Path
  )
  if (-not $Path) { return }
  if (-not $Candidates.Contains($Path)) {
    [void]$Candidates.Add($Path)
  }
}

function Get-OSRootCandidates {
  param([string]$RepoRoot)
  $candidates = [System.Collections.Generic.List[string]]::new()

  Add-OSRootCandidate $candidates $env:PERSONAL_OS_ROOT
  Add-OSRootCandidate $candidates $env:PERSONAL_OS_SDK_ROOT
  if ($env:PERSONAL_OS_SDK_ROOT -and ((Split-Path -Leaf $env:PERSONAL_OS_SDK_ROOT) -eq "os-sdk")) {
    $sdkParent = Split-Path -Parent $env:PERSONAL_OS_SDK_ROOT
    $systemParent = if ($sdkParent) { Split-Path -Parent $sdkParent } else { "" }
    $rootFromSdk = if ($systemParent) { Split-Path -Parent $systemParent } else { "" }
    Add-OSRootCandidate $candidates $rootFromSdk
  }

  Add-OSRootCandidate $candidates (Join-Path $RepoRoot "personal_os")

  $repoParent = Split-Path -Parent $RepoRoot
  if ($repoParent) {
    Add-OSRootCandidate $candidates (Join-Path $repoParent "OS")
    $repoGrandParent = Split-Path -Parent $repoParent
    if ($repoGrandParent) {
      Add-OSRootCandidate $candidates (Join-Path $repoGrandParent "OS")
      Add-OSRootCandidate $candidates (Join-Path $repoGrandParent "Desktop\OS")
    }
  }

  $userHome = [Environment]::GetFolderPath("UserProfile")
  Add-OSRootCandidate $candidates (Join-Path $userHome "OneDrive - Office\Desktop\OS")
  Add-OSRootCandidate $candidates (Join-Path $userHome "OneDrive\Desktop\OS")
  Add-OSRootCandidate $candidates (Join-Path $userHome "Desktop\OS")

  return $candidates
}

function Resolve-ExistingDirectory {
  param([string]$Path)
  if (-not (Test-ExistingDirectory $Path)) { return "" }
  try {
    return (Resolve-Path -LiteralPath $Path).Path
  } catch {
    return ""
  }
}

function Get-OSRootScore {
  param([string]$Path)
  if (-not (Test-ExistingDirectory $Path)) { return 0 }
  $score = 0
  foreach ($subdir in $ExpectedOsSubdirs) {
    if (Test-ExistingDirectory (Join-Path $Path $subdir)) {
      $score += 1
    }
  }
  return $score
}

function Select-OSRootCandidate {
  param([string[]]$Candidates)
  $bestPath = ""
  $bestScore = 0
  foreach ($candidate in $Candidates) {
    $resolved = Resolve-ExistingDirectory $candidate
    if (-not $resolved) { continue }
    $score = Get-OSRootScore $resolved
    if ($score -gt $bestScore) {
      $bestPath = $resolved
      $bestScore = $score
    }
  }
  return $bestPath
}

if ($OSRoot) {
  $OSRoot = Resolve-ExistingDirectory $OSRoot
} else {
  $OSRoot = Select-OSRootCandidate (Get-OSRootCandidates $RepoRoot)
}

if (-not $OSRoot -or !(Test-Path -LiteralPath $OSRoot)) {
  $message = "OS root not found. Set -OSRoot, PERSONAL_OS_ROOT, PERSONAL_OS_SDK_ROOT, or mount personal_os."
  if ($AllowMissing) { Write-Warning $message; exit 0 }
  throw $message
}

function Invoke-Step {
  param([string]$Name, [scriptblock]$Command)
  Write-Host ""
  Write-Host "== $Name =="
  & $Command
  if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
}

function Invoke-TscNoInstall {
  param([string]$Dir, [string]$Name)
  if (!(Test-Path -LiteralPath $Dir)) { Write-Warning "$Name path missing: $Dir"; return }
  if (!(Test-Path -LiteralPath (Join-Path $Dir "tsconfig.json"))) { Write-Warning "$Name tsconfig missing."; return }
  Push-Location $Dir
  try {
    Invoke-Step "$Name TypeScript" { npx.cmd --no-install tsc -p tsconfig.json --noEmit }
  } finally {
    Pop-Location
  }
}

function Invoke-NpmScriptIfPresent {
  param([string]$Dir, [string]$ScriptName, [string]$Label, [string[]]$ScriptArgs = @())
  $pkgPath = Join-Path $Dir "package.json"
  if (!(Test-Path -LiteralPath $pkgPath)) { return }
  $pkg = Get-Content -LiteralPath $pkgPath -Raw | ConvertFrom-Json
  if (-not $pkg.scripts.$ScriptName) { return }
  Push-Location $Dir
  try {
    Invoke-Step $Label { npm.cmd run $ScriptName -- @ScriptArgs }
  } finally {
    Pop-Location
  }
}

Write-Host "OS quality gates"
Write-Host "OSRoot: $OSRoot"

$sdk = Join-Path $OSRoot "00_System\SDK\os-sdk"
$mcp = Join-Path $OSRoot "11_Integrations\MCP\os-mcp-server"
$worker = Join-Path $OSRoot "07_Automations\Workflows\raw-inbox-worker"

Invoke-TscNoInstall $sdk "OS SDK"
Invoke-NpmScriptIfPresent $sdk "drafts" "OS SDK draft check" @("--hide-smoke")
Invoke-NpmScriptIfPresent $sdk "phase2a:smoke" "OS SDK phase2a smoke"
Invoke-NpmScriptIfPresent $sdk "smoke" "OS SDK smoke"

Invoke-TscNoInstall $mcp "OS MCP server"
Invoke-NpmScriptIfPresent $mcp "check" "OS MCP server check"

Invoke-TscNoInstall $worker "Raw Inbox Worker"
Invoke-NpmScriptIfPresent $worker "check" "Raw Inbox Worker check"

Write-Host "OS quality gates completed without deleting, migrating, or archiving drafts."
exit 0

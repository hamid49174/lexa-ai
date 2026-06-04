param(
  [string]$RepoRoot = "",
  [string]$OSRoot = "",
  [string]$WebsiteRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
} else {
  $RepoRoot = Resolve-Path -LiteralPath $RepoRoot
}

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

if (-not $WebsiteRoot) {
  $candidate = Resolve-Path -LiteralPath (Join-Path $RepoRoot "..\lexa-website") -ErrorAction SilentlyContinue
  if ($candidate) { $WebsiteRoot = $candidate.Path }
}

$warnings = New-Object System.Collections.Generic.List[string]
$NodeLockfiles = @("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml")

function Add-Warn([string]$Message) {
  $warnings.Add($Message) | Out-Null
  Write-Warning $Message
}

function Resolve-CommandPath {
  param(
    [string[]]$Names,
    [string[]]$Candidates = @()
  )
  foreach ($candidate in $Candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
      return $candidate
    }
  }
  foreach ($name in $Names) {
    try {
      $cmd = Get-Command $name -ErrorAction Stop
      if ($cmd.Source) { return $cmd.Source }
      if ($cmd.Path) { return $cmd.Path }
    } catch {
      continue
    }
  }
  return ""
}

function Show-CommandVersion([string]$Label, [string[]]$Names, [string[]]$VersionArgs, [string[]]$Candidates = @()) {
  $commandPath = Resolve-CommandPath $Names $Candidates
  if (-not $commandPath) {
    Add-Warn "$Label not available."
    return
  }
  try {
    $output = & $commandPath @VersionArgs 2>$null | Select-Object -First 1
    Write-Host "${Label}: $output"
  } catch {
    Add-Warn "$Label version check failed."
  }
}

function Test-File([string]$PathValue, [string]$Label, [bool]$Required = $true) {
  if (Test-Path -LiteralPath $PathValue -PathType Leaf) {
    Write-Host "ok: $Label"
  } elseif (Test-Path -LiteralPath $PathValue) {
    Add-Warn "not a file: $Label ($PathValue)"
  } elseif ($Required) {
    Add-Warn "missing: $Label ($PathValue)"
  } else {
    Write-Host "optional missing: $Label"
  }
}

function Test-NodeLockfileCoverage([string]$Directory, [string]$Label, [bool]$Required = $true) {
  $existingLockfiles = @($NodeLockfiles | Where-Object { Test-Path -LiteralPath (Join-Path $Directory $_) -PathType Leaf })
  $nonFileLockfiles = @($NodeLockfiles | Where-Object {
    $lockfilePath = Join-Path $Directory $_
    (Test-Path -LiteralPath $lockfilePath) -and -not (Test-Path -LiteralPath $lockfilePath -PathType Leaf)
  })
  $packagePath = Join-Path $Directory "package.json"
  $packageExists = Test-Path -LiteralPath $packagePath
  $hasPackage = Test-Path -LiteralPath $packagePath -PathType Leaf
  if ($packageExists -and -not $hasPackage) {
    Add-Warn "not a file: $Label package.json ($packagePath)"
    return
  }
  if ($nonFileLockfiles.Count -gt 0) {
    Add-Warn "$Label lockfile path is not a file: $($nonFileLockfiles -join ', ')"
    return
  }
  if (-not $hasPackage -and $existingLockfiles.Count -eq 0) {
    if ($Required) {
      Add-Warn "missing: $Label package.json and lockfile ($packagePath)"
    }
    return
  }
  if (-not $hasPackage -and $existingLockfiles.Count -gt 0) {
    Add-Warn "$Label lockfile exists without package.json: $($existingLockfiles -join ', ')"
    return
  }
  if ($existingLockfiles.Count -eq 0) {
    $expected = $NodeLockfiles -join ", "
    if ($Required) {
      Add-Warn "missing: $Label lockfile (one of: $expected)"
    } else {
      Add-Warn "missing: $Label lockfile for package.json (one of: $expected)"
    }
    return
  }

  Write-Host "ok: $Label lockfile ($($existingLockfiles -join ', '))"
  if ($existingLockfiles.Count -gt 1) {
    Add-Warn "multiple $Label lockfiles found: $($existingLockfiles -join ', ')"
  }
}

Write-Host "Lexa dependency reproducibility check"
Write-Host "RepoRoot: $RepoRoot"
Show-CommandVersion "python" @("python") @("--version") @((Join-Path $RepoRoot "venv\Scripts\python.exe"))
Show-CommandVersion "node" @("node") @("--version")
Show-CommandVersion "npm" @("npm.cmd", "npm") @("--version")

Test-File (Join-Path $RepoRoot "requirements.txt") "Python requirements"
Test-File (Join-Path $RepoRoot "requirements-dev.txt") "Python dev requirements" $false
Test-File (Join-Path $RepoRoot "pytest.ini") "pytest config"
Test-NodeLockfileCoverage (Join-Path $RepoRoot "frontend") "frontend"

if ($OSRoot -and (Test-ExistingDirectory $OSRoot)) {
  Write-Host "OSRoot: $OSRoot"
  foreach ($rel in @(
    "00_System\SDK\os-sdk",
    "11_Integrations\MCP\os-mcp-server",
    "07_Automations\Workflows\raw-inbox-worker"
  )) {
    $dir = Join-Path $OSRoot $rel
    Test-NodeLockfileCoverage $dir $rel $false
  }
} else {
  Add-Warn "OS root not found; OS dependency reproducibility was not checked."
}

if ($WebsiteRoot -and (Test-Path -LiteralPath $WebsiteRoot)) {
  Write-Host "WebsiteRoot: $WebsiteRoot"
  Test-NodeLockfileCoverage $WebsiteRoot "website" $false
} else {
  Write-Host "Website root not found; website dependency check is skipped."
}

Write-Host "Dependency reproducibility check completed with $($warnings.Count) warning(s)."
exit 0

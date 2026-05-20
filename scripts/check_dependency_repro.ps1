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

if (-not $OSRoot) {
  $junction = Join-Path $RepoRoot "personal_os"
  if (Test-Path -LiteralPath $junction) { $OSRoot = (Resolve-Path -LiteralPath $junction).Path }
}

if (-not $WebsiteRoot) {
  $candidate = Resolve-Path -LiteralPath (Join-Path $RepoRoot "..\lexa-website") -ErrorAction SilentlyContinue
  if ($candidate) { $WebsiteRoot = $candidate.Path }
}

$warnings = New-Object System.Collections.Generic.List[string]

function Add-Warn([string]$Message) {
  $warnings.Add($Message) | Out-Null
  Write-Warning $Message
}

function Show-CommandVersion([string]$Name, [string[]]$Args) {
  try {
    $cmd = Get-Command $Name -ErrorAction Stop
    $output = & $cmd.Source @Args 2>$null | Select-Object -First 1
    Write-Host "${Name}: $output"
  } catch {
    Add-Warn "$Name not available on PATH."
  }
}

function Test-File([string]$PathValue, [string]$Label, [bool]$Required = $true) {
  if (Test-Path -LiteralPath $PathValue) {
    Write-Host "ok: $Label"
  } elseif ($Required) {
    Add-Warn "missing: $Label ($PathValue)"
  } else {
    Write-Host "optional missing: $Label"
  }
}

Write-Host "Lexa dependency reproducibility check"
Write-Host "RepoRoot: $RepoRoot"
Show-CommandVersion "python" @("--version")
Show-CommandVersion "node" @("--version")
Show-CommandVersion "npm" @("--version")

Test-File (Join-Path $RepoRoot "requirements.txt") "Python requirements"
Test-File (Join-Path $RepoRoot "requirements-dev.txt") "Python dev requirements" $false
Test-File (Join-Path $RepoRoot "pytest.ini") "pytest config"
Test-File (Join-Path $RepoRoot "frontend\package.json") "frontend package.json"
Test-File (Join-Path $RepoRoot "frontend\package-lock.json") "frontend npm lockfile"

if ($OSRoot -and (Test-Path -LiteralPath $OSRoot)) {
  Write-Host "OSRoot: $OSRoot"
  foreach ($rel in @(
    "00_System\SDK\os-sdk",
    "11_Integrations\MCP\os-mcp-server",
    "07_Automations\Workflows\raw-inbox-worker"
  )) {
    $dir = Join-Path $OSRoot $rel
    Test-File (Join-Path $dir "package.json") "$rel package.json" $false
    Test-File (Join-Path $dir "package-lock.json") "$rel lockfile" $false
  }
} else {
  Add-Warn "OS root not found; OS dependency reproducibility was not checked."
}

if ($WebsiteRoot -and (Test-Path -LiteralPath $WebsiteRoot)) {
  Write-Host "WebsiteRoot: $WebsiteRoot"
  Test-File (Join-Path $WebsiteRoot "package.json") "website package.json" $false
  Test-File (Join-Path $WebsiteRoot "package-lock.json") "website lockfile" $false
} else {
  Write-Host "Website root not found; website dependency check is skipped."
}

Write-Host "Dependency reproducibility check completed with $($warnings.Count) warning(s)."
exit 0

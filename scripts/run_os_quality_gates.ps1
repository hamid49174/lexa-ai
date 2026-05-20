param(
  [string]$OSRoot = "",
  [switch]$AllowMissing
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")

if (-not $OSRoot) {
  $junction = Join-Path $RepoRoot "personal_os"
  if (Test-Path -LiteralPath $junction) { $OSRoot = (Resolve-Path -LiteralPath $junction).Path }
}

if (-not $OSRoot -or !(Test-Path -LiteralPath $OSRoot)) {
  $message = "OS root not found. Set -OSRoot or mount personal_os."
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

param(
  [switch]$SkipBackend,
  [switch]$UseNpmCi
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$FrontendRoot = Join-Path $RepoRoot "frontend"
$BackendDist = Join-Path $RepoRoot "backend-dist\lexa-backend"
$VenvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"

function Invoke-Step {
  param([string]$Name, [scriptblock]$Command)
  Write-Host ""
  Write-Host "== $Name =="
  & $Command
  if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
}

if (-not $SkipBackend) {
  $Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }
  Invoke-Step "Build backend bundle" { & $Python (Join-Path $RepoRoot "build_backend.py") }
}

if (!(Test-Path -LiteralPath $BackendDist)) {
  throw "Backend bundle missing: $BackendDist. Run scripts\build_installer.ps1 without -SkipBackend first."
}

Push-Location $FrontendRoot
try {
  if ($UseNpmCi -or !(Test-Path -LiteralPath (Join-Path $FrontendRoot "node_modules"))) {
    Invoke-Step "Install frontend dependencies" { npm.cmd ci }
  }
  Invoke-Step "Build Electron installer" { npm.cmd run build }
} finally {
  Pop-Location
}

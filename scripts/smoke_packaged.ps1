param(
  [string]$AppPath = "",
  [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
if (-not $AppPath) {
  $AppPath = Join-Path $repoRoot "dist\win-unpacked\Lexa AI.exe"
}

if (-not (Test-Path -LiteralPath $AppPath)) {
  throw "Packaged app not found: $AppPath. Run 'npm.cmd run build' from frontend first."
}

$workDir = Split-Path -Parent $AppPath
$app = Start-Process -FilePath $AppPath -WorkingDirectory $workDir -WindowStyle Hidden -PassThru

try {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 1
    if ($app.HasExited) {
      throw "Lexa packaged app exited before /health became available."
    }

    try {
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
      if ($health.status -eq "ok") {
        Write-Host "Packaged smoke passed: /health status ok, version $($health.version)"
        exit 0
      }
    } catch {
      # Backend is still starting.
    }
  }

  throw "Timed out waiting for packaged Lexa backend health."
} finally {
  if ($app -and -not $app.HasExited) {
    Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
  }
  Get-Process | Where-Object {
    $_.ProcessName -eq "Lexa AI" -or $_.ProcessName -eq "lexa-backend"
  } | Stop-Process -Force -ErrorAction SilentlyContinue
}

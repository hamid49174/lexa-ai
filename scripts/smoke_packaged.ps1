param(
  [string]$AppPath = "",
  [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"

function Get-LexaPackagedSmokeProcesses {
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -eq "Lexa AI.exe" -or $_.Name -eq "lexa-backend.exe"
  }
}

function Invoke-LexaPackagedHealthProbe {
  try {
    return Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
  } catch {
    return $null
  }
}

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
if (-not $AppPath) {
  $AppPath = Join-Path $repoRoot "dist\win-unpacked\Lexa AI.exe"
}

if (-not (Test-Path -LiteralPath $AppPath)) {
  throw "Packaged app not found: $AppPath. Run 'npm.cmd run build' from frontend first."
}

$baselineProcessIds = @{}
Get-LexaPackagedSmokeProcesses | ForEach-Object {
  $baselineProcessIds[[int]$_.ProcessId] = $true
}

if (Invoke-LexaPackagedHealthProbe) {
  throw "Port 8000 already answered /health before packaged app start; stop the existing Lexa backend before running packaged smoke."
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
      $health = Invoke-LexaPackagedHealthProbe
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
  $ownedProcessIds = @{}
  if ($app) {
    $ownedProcessIds[[int]$app.Id] = $true
  }

  $changed = $true
  while ($changed) {
    $changed = $false
    Get-LexaPackagedSmokeProcesses | Where-Object {
      -not $baselineProcessIds.ContainsKey([int]$_.ProcessId)
    } | ForEach-Object {
      $processId = [int]$_.ProcessId
      $parentProcessId = [int]$_.ParentProcessId
      if (-not $ownedProcessIds.ContainsKey($processId) -and $ownedProcessIds.ContainsKey($parentProcessId)) {
        $ownedProcessIds[$processId] = $true
        $changed = $true
      }
    }
  }

  Get-LexaPackagedSmokeProcesses | Where-Object {
    $ownedProcessIds.ContainsKey([int]$_.ProcessId)
  } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
}

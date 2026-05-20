param(
  [string]$ArtifactRoot = "",
  [string]$InstallerPath = "",
  [switch]$RequireInstaller
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")

if (-not $ArtifactRoot) {
  $ArtifactRoot = Join-Path $RepoRoot "dist"
}

$forbiddenRegex = '(?i)(personal_os|hermes_workspace|evals[\\/]+results|tmp[\\/]+agent_traces|lexa_memory\.db|bridge-audit\.log|audit\.log|\.env$|\.env[\\/]|(^|[\\/])secrets?([\\/]|$)|private[_-]?key|STRIPE_SECRET|SUPABASE_SERVICE_ROLE)'

Write-Host "Lexa installer smoke"
Write-Host "ArtifactRoot: $ArtifactRoot"

if ($InstallerPath) {
  if (!(Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
    throw "InstallerPath not found: $InstallerPath"
  }
  $installer = Get-Item -LiteralPath $InstallerPath
} elseif (Test-Path -LiteralPath $ArtifactRoot) {
  $candidates = @(Get-ChildItem -LiteralPath $ArtifactRoot -Recurse -Force -File -Include "*.exe", "*.msi", "*.msix" -ErrorAction SilentlyContinue | Sort-Object Length -Descending)
  $installer = $candidates | Select-Object -First 1
} else {
  $installer = $null
}

if (-not $installer) {
  $message = "No installer artifact found. Installer smoke is not yet proven."
  if ($RequireInstaller) { throw $message }
  Write-Warning $message
  exit 0
}

if ($installer.FullName -match $forbiddenRegex) {
  throw "Installer path itself looks risky: $($installer.FullName)"
}

if ($installer.Length -lt 1MB) {
  throw "Installer artifact is unexpectedly small: $($installer.FullName) ($($installer.Length) bytes)"
}

if (Test-Path -LiteralPath $ArtifactRoot) {
  $forbidden = @()
  Get-ChildItem -LiteralPath $ArtifactRoot -Recurse -Force -File -ErrorAction SilentlyContinue | ForEach-Object {
    $relative = $_.FullName.Substring((Resolve-Path -LiteralPath $ArtifactRoot).Path.Length).TrimStart('\', '/')
    if ($relative -match $forbiddenRegex -or $_.Name -match '(?i)^(\.env|audit\.log|bridge-audit\.log|lexa_memory\.db|lexa_memory\.db-|.*\.env$)') {
      $forbidden += $relative
    }
  }
  if ($forbidden.Count -gt 0) {
    throw "Forbidden content found near installer artifacts: $($forbidden -join ', ')"
  }
}

Write-Host "Installer smoke completed."
Write-Host "Installer: $($installer.FullName)"
Write-Host "Size bytes: $($installer.Length)"
Write-Host "Signing status: unsigned/not verified by this smoke."
exit 0

param(
  [string]$ArtifactRoot = "",
  [string]$InstallerPath = "",
  [switch]$RequireInstaller,
  [switch]$Install,
  [switch]$Uninstall,
  [switch]$VMOnly,
  [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")

if (-not $ArtifactRoot) {
  $ArtifactRoot = Join-Path $RepoRoot "dist"
}

$forbiddenRegex = '(?i)(personal_os|hermes_workspace|evals[\\/]+results|tmp[\\/]+agent_traces|lexa_memory\.db|bridge-audit\.log|audit\.log|\.env$|\.env[\\/]|(^|[\\/])secrets?([\\/]|$)|private[_-]?key|STRIPE_SECRET|SUPABASE_SERVICE_ROLE)'

Write-Host "Lexa installer smoke"
Write-Host "ArtifactRoot: $ArtifactRoot"
Write-Host "Install requested: $Install Uninstall requested: $Uninstall VMOnly: $VMOnly PlanOnly: $PlanOnly"

function Get-SigningStatus {
  param([string]$PathValue)
  try {
    $signature = Get-AuthenticodeSignature -LiteralPath $PathValue -ErrorAction Stop
    if ($signature.Status -eq "Valid") { return "signed" }
    if ($signature.Status -eq "NotSigned") { return "unsigned" }
    return "unknown:$($signature.Status)"
  } catch {
    return "unknown"
  }
}

function Test-WindowsSandboxAvailable {
  try {
    $feature = Get-WindowsOptionalFeature -Online -FeatureName "Containers-DisposableClientVM" -ErrorAction Stop
    return ($feature.State -eq "Enabled")
  } catch {
    return $false
  }
}

function Write-InstallPlan {
  param([string]$PathValue)
  Write-Host "Installer VM install/uninstall plan:"
  Write-Host "1. Use a disposable Windows VM or Windows Sandbox only."
  Write-Host "2. Copy the installer into the isolated machine: $PathValue"
  Write-Host "3. Install Lexa AI, launch once, and run startup smoke against isolated userData."
  Write-Host "4. Uninstall Lexa AI from the VM/sandbox."
  Write-Host "5. Check no user data, .env, memory DB, OS vault data, Hermes workspace, or logs were bundled."
  Write-Host "6. Destroy or revert the VM/sandbox snapshot."
  Write-Host "This script does not perform productive-machine install/uninstall."
}

if (($Install -or $Uninstall) -and -not $VMOnly) {
  throw "Installer install/uninstall smoke requires -VMOnly. Do not install into the productive machine from this script."
}

if ($PlanOnly) {
  Write-InstallPlan "<installer-path>"
  Write-Warning "Plan-only mode does not prove installer install/uninstall."
  exit 0
}

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
Write-Host "Signing status: $(Get-SigningStatus $installer.FullName)"
if ($Install -or $Uninstall) {
  $sandboxAvailable = Test-WindowsSandboxAvailable
  Write-Host "Windows Sandbox available: $sandboxAvailable"
  Write-InstallPlan $installer.FullName
  Write-Warning "Installer install/uninstall proof is prepared as VM-only and was not executed automatically. Run inside a disposable VM/sandbox with explicit human approval."
  Write-Host "Installer install/uninstall status: not yet proven by this local smoke."
} else {
  Write-Host "Installer install/uninstall status: not requested; not yet proven."
}
exit 0

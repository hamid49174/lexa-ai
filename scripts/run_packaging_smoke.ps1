param(
  [string]$RepoRoot = "",
  [switch]$Build,
  [string]$ArtifactRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
} else {
  $RepoRoot = Resolve-Path -LiteralPath $RepoRoot
}

$frontendRoot = Join-Path $RepoRoot "frontend"
$packageJson = Join-Path $frontendRoot "package.json"
$builderConfig = Join-Path $frontendRoot "electron-builder.json"
$backendDist = Join-Path $RepoRoot "backend-dist\lexa-backend"
$forbiddenNames = @(".env", "audit.log", "bridge-audit.log", "lexa_memory.db")
$forbiddenPathRegex = '(?i)(personal_os|hermes_workspace|evals[\\/]+results|tmp[\\/]+agent_traces|lexa_memory\.db|bridge-audit\.log|audit\.log|\.env$|\.env[\\/])'

if (-not $ArtifactRoot) {
  if ($Build) {
    $ArtifactRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("lexa-packaging-smoke-" + [guid]::NewGuid().ToString("N"))
  } else {
    $ArtifactRoot = Join-Path $RepoRoot "dist"
  }
}

function Assert-File([string]$PathValue, [string]$Label) {
  if (!(Test-Path -LiteralPath $PathValue)) { throw "$Label not found: $PathValue" }
  Write-Host "ok: $Label"
}

function Test-ForbiddenArtifactContent([string]$PathValue) {
  if (!(Test-Path -LiteralPath $PathValue)) {
    Write-Host "Artifact path does not exist yet: $PathValue"
    return
  }
  $hits = @()
  Get-ChildItem -LiteralPath $PathValue -Recurse -Force -File -ErrorAction SilentlyContinue | ForEach-Object {
    $relative = $_.FullName.Substring((Resolve-Path -LiteralPath $PathValue).Path.Length).TrimStart('\', '/')
    if ($_.Name -in $forbiddenNames -or $relative -match $forbiddenPathRegex -or $_.Name -match '(?i)^lexa_memory\.db') {
      $hits += $relative
    }
  }
  if ($hits.Count -gt 0) {
    throw "Forbidden files found in build artifacts: $($hits -join ', ')"
  }
  Write-Host "ok: no forbidden files found in artifact path $PathValue"
}

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

Write-Host "Lexa packaging smoke"
Write-Host "RepoRoot: $RepoRoot"
Assert-File $packageJson "frontend package.json"
Assert-File $builderConfig "electron-builder config"

$package = Get-Content -LiteralPath $packageJson -Raw | ConvertFrom-Json
if (-not $package.scripts.build) { throw "frontend/package.json has no build script." }
Write-Host "Build command: npm run build"

$builder = Get-Content -LiteralPath $builderConfig -Raw | ConvertFrom-Json
$filesJson = ($builder.files | ConvertTo-Json -Compress)
$resourcesJson = ($builder.extraResources | ConvertTo-Json -Compress)
if ($filesJson -match '\.\.[\\/]\*\*' -or $resourcesJson -match '\.\.[\\/]\*\*') {
  throw "electron-builder config includes overly broad parent-directory globs."
}
if ($filesJson -match $forbiddenPathRegex -or $resourcesJson -match $forbiddenPathRegex) {
  throw "electron-builder config references forbidden local/user-data paths."
}
Write-Host "ok: electron-builder config does not include broad or forbidden paths"

if ($Build) {
  if (!(Test-Path -LiteralPath $backendDist)) {
    throw "backend-dist/lexa-backend is required for a full Electron package build and was not found: $backendDist"
  }
  New-Item -ItemType Directory -Path $ArtifactRoot -Force | Out-Null
  Push-Location $frontendRoot
  try {
    npx.cmd --no-install electron-builder --config electron-builder.json "--config.directories.output=$ArtifactRoot"
  } finally {
    Pop-Location
  }
} else {
  Write-Host "Build execution skipped. Use -Build for an isolated local package build smoke."
}

Test-ForbiddenArtifactContent $ArtifactRoot

$installers = @()
if (Test-Path -LiteralPath $ArtifactRoot) {
  $installers = @(Get-ChildItem -LiteralPath $ArtifactRoot -Recurse -Force -File -Include "*.exe", "*.msi", "*.msix" -ErrorAction SilentlyContinue | Sort-Object Length -Descending)
}
if ($installers.Count -gt 0) {
  $primaryInstaller = $installers | Select-Object -First 1
  Write-Host "Installer signing status: $(Get-SigningStatus $primaryInstaller.FullName)"
} else {
  Write-Host "Installer signing status: not checked; no installer artifact found."
}

$stagedArtifacts = @(git -C $RepoRoot diff --cached --name-only -- dist backend-dist frontend/dist build 2>$null)
if ($stagedArtifacts.Count -gt 0) {
  throw "Build artifacts are staged: $($stagedArtifacts -join ', ')"
}
Write-Host "ok: no build artifacts are staged"
Write-Host "Packaging smoke completed. Artifact path: $ArtifactRoot"
exit 0

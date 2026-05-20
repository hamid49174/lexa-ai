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

if (-not $ArtifactRoot) {
  $ArtifactRoot = Join-Path $RepoRoot "dist"
}

$frontendRoot = Join-Path $RepoRoot "frontend"
$packageJson = Join-Path $frontendRoot "package.json"
$builderConfig = Join-Path $frontendRoot "electron-builder.json"
$forbiddenNames = @(".env", "audit.log", "bridge-audit.log", "lexa_memory.db")
$forbiddenPathRegex = '(?i)(personal_os|hermes_workspace|evals[\\/]+results|tmp[\\/]+agent_traces|lexa_memory\.db|bridge-audit\.log|audit\.log|\.env$|\.env[\\/])'

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
  Push-Location $frontendRoot
  try {
    npm.cmd run build
  } finally {
    Pop-Location
  }
} else {
  Write-Host "Build execution skipped. Use -Build for a local package build smoke."
}

Test-ForbiddenArtifactContent $ArtifactRoot

$stagedArtifacts = @(git -C $RepoRoot diff --cached --name-only -- dist backend-dist frontend/dist build 2>$null)
if ($stagedArtifacts.Count -gt 0) {
  throw "Build artifacts are staged: $($stagedArtifacts -join ', ')"
}
Write-Host "ok: no build artifacts are staged"
Write-Host "Packaging smoke completed. Artifact path: $ArtifactRoot"
exit 0

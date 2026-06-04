param(
  [string]$RepoRoot = "",
  [switch]$Build,
  [string]$ArtifactRoot = "",
  [switch]$KeepArtifactRoot
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
} else {
  $RepoRoot = Resolve-Path -LiteralPath $RepoRoot
}

$frontendRoot = Join-Path $RepoRoot "frontend"
$packageJson = Join-Path $frontendRoot "package.json"
$packageLock = Join-Path $frontendRoot "package-lock.json"
$npmShrinkwrap = Join-Path $frontendRoot "npm-shrinkwrap.json"
$yarnLock = Join-Path $frontendRoot "yarn.lock"
$pnpmLock = Join-Path $frontendRoot "pnpm-lock.yaml"
$packageSecretScanPaths = @($packageJson, $packageLock, $npmShrinkwrap, $yarnLock, $pnpmLock)
$builderConfig = Join-Path $frontendRoot "electron-builder.json"
$backendDist = Join-Path $RepoRoot "backend-dist\lexa-backend"
$forbiddenNames = @(".env", "audit.log", "bridge-audit.log", "lexa_memory.db")
$forbiddenPathRegex = '(?i)(personal_os|hermes_workspace|evals[\\/]+results|tmp[\\/]+agent_traces|lexa_memory\.db|bridge-audit\.log|audit\.log|\.env$|\.env[\\/])'
$riskyConfigPathRegex = '(?i)((^|[\\/]+)\.env(?=$|["},:\]\s]|\.|[\\/]+)|(^|[\\/]+)\.(netrc|npmrc|pnpmrc|pypirc)(?=$|["},:\]\s])|(^|[\\/]+)\.yarnrc(\.yml)?(?=$|["},:\]\s])|(^|[\\/]+)\.aws[\\/]+(credentials|config)(?=$|["},:\]\s])|(^|[\\/]+)\.azure[\\/]+(accessTokens|azureProfile)\.json(?=$|["},:\]\s])|(^|[\\/]+)(\.config[\\/]+gcloud|\.gcloud)[\\/]+application_default_credentials\.json(?=$|["},:\]\s])|(^|[\\/]+)\.docker[\\/]+config\.json(?=$|["},:\]\s])|(^|[\\/]+)\.kube[\\/]+config(?=$|["},:\]\s])|(^|[\\/]+)(credentials|secrets)\.(json|ya?ml|toml|ini|conf)(?=$|["},:\]\s])|(^|[\\/]+)client_secret[^\\/]*\.json(?=$|["},:\]\s])|(^|[\\/]+)service[-_]?account[^\\/]*\.json(?=$|["},:\]\s])|(^|[\\/]+)\.ssh[\\/]+(id_dsa|id_ecdsa|id_ed25519|id_rsa)(?=$|["},:\]\s])|(^|[\\/]+)(id_dsa|id_ecdsa|id_ed25519|id_rsa)(?=$|["},:\]\s])|(^|[\\/]+)pip\.(conf|ini)(?=$|["},:\]\s])|\.(pfx|p12|pem|ppk|key|pvk|cer|crt|spc|jks|keystore)(?=$|["},:\]\s])|(codesign|code-sign|signing|signtool)[^\\/]*\.(json|ya?ml|toml|ini|conf|txt|env|xml)(?=$|["},:\]\s])|(windows|electron)[_-]?(signing|certificate|cert)[^\\/]*\.(json|ya?ml|toml|ini|conf|txt|env|xml)(?=$|["},:\]\s]))'

$artifactRootWasProvided = -not [string]::IsNullOrWhiteSpace($ArtifactRoot)
$generatedArtifactRoot = $false
if (-not $ArtifactRoot) {
  if ($Build) {
    $ArtifactRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("lexa-packaging-smoke-" + [guid]::NewGuid().ToString("N"))
    $generatedArtifactRoot = $true
  } else {
    $ArtifactRoot = Join-Path $RepoRoot "dist"
  }
}

function Assert-File([string]$PathValue, [string]$Label) {
  if (Test-Path -LiteralPath $PathValue -PathType Leaf) {
    Write-Host "ok: $Label"
    return
  }
  if (Test-Path -LiteralPath $PathValue) { throw "$Label is not a file: $PathValue" }
  throw "$Label not found: $PathValue"
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

function Invoke-RiskyArtifactPathCheck([string]$PathValue) {
  if (!(Test-Path -LiteralPath $PathValue)) { return }
  & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "check_risky_artifacts.ps1") -Root $RepoRoot -Mode Strict -ArtifactPath $PathValue
  if ($LASTEXITCODE -ne 0) {
    throw "Risky artifact check failed for artifact path: $PathValue"
  }
}

function Invoke-RiskySecretScanPathCheck([string]$PathValue) {
  if (!(Test-Path -LiteralPath $PathValue -PathType Leaf)) { return }
  & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "check_risky_artifacts.ps1") -Root $RepoRoot -Mode Strict -SecretScanPath $PathValue
  if ($LASTEXITCODE -ne 0) {
    throw "Risky secret scan failed for path: $PathValue"
  }
}

function ConvertTo-RiskyConfigScanText([object]$ConfigValue) {
  $json = ($ConfigValue | ConvertTo-Json -Depth 20 -Compress)
  return ($json -replace '"![^"]*"', '""')
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
foreach ($packageSecretScanPath in $packageSecretScanPaths) {
  Invoke-RiskySecretScanPathCheck $packageSecretScanPath
}
Invoke-RiskySecretScanPathCheck $builderConfig

$package = Get-Content -LiteralPath $packageJson -Raw | ConvertFrom-Json
if (-not $package.scripts.build) { throw "frontend/package.json has no build script." }
Write-Host "Build command: npm run build"

$builder = Get-Content -LiteralPath $builderConfig -Raw | ConvertFrom-Json
$builderRiskScanJson = ConvertTo-RiskyConfigScanText $builder
$filesJson = ($builder.files | ConvertTo-Json -Compress)
$resourcesJsonAll = ($builder.extraResources | ConvertTo-Json -Compress)
$resourcesForForbiddenScan = @($builder.extraResources | ForEach-Object {
  [pscustomobject]@{
    from = $_.from
    to = $_.to
    filter = @($_.filter | Where-Object { -not ([string]$_).StartsWith("!") })
  }
})
$resourcesJson = ($resourcesForForbiddenScan | ConvertTo-Json -Compress)
if ($filesJson -match '\.\.[\\/]\*\*' -or $resourcesJsonAll -match '\.\.[\\/]\*\*') {
  throw "electron-builder config includes overly broad parent-directory globs."
}
if ($filesJson -match $forbiddenPathRegex -or $resourcesJson -match $forbiddenPathRegex -or $builderRiskScanJson -match $riskyConfigPathRegex) {
  throw "electron-builder config references forbidden local/user-data, credential, or signing paths."
}
$backendResource = @($builder.extraResources | Where-Object { $_.from -eq "../backend-dist/lexa-backend" }) | Select-Object -First 1
if (-not $backendResource) {
  throw "electron-builder config does not package the backend bundle."
}
$backendFilters = @($backendResource.filter)
foreach ($requiredFilter in @("!**/audit.log", "!**/bridge-audit.log", "!**/lexa_memory.db*")) {
  if ($requiredFilter -notin $backendFilters) {
    throw "electron-builder backend resource filter is missing runtime artifact exclusion: $requiredFilter"
  }
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
    if ($LASTEXITCODE -ne 0) {
      throw "electron-builder failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }

  $packagedApp = Join-Path $ArtifactRoot "win-unpacked\Lexa AI.exe"
  if (!(Test-Path -LiteralPath $packagedApp)) {
    throw "Packaged app runtime smoke target not found after build: $packagedApp"
  }
  powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "smoke_packaged.ps1") -AppPath $packagedApp -TimeoutSeconds 45
  if ($LASTEXITCODE -ne 0) {
    throw "Packaged runtime smoke failed with exit code $LASTEXITCODE"
  }
} else {
  Write-Host "Build execution skipped. Use -Build for an isolated local package build smoke."
}

Test-ForbiddenArtifactContent $ArtifactRoot
Invoke-RiskyArtifactPathCheck $ArtifactRoot

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

$stagedArtifacts = @(git -C $RepoRoot diff --cached --name-only -- dist "dist-*-build" backend-dist frontend/dist build 2>$null)
if ($stagedArtifacts.Count -gt 0) {
  throw "Build artifacts are staged: $($stagedArtifacts -join ', ')"
}
Write-Host "ok: no build artifacts are staged"
Write-Host "Packaging smoke completed. Artifact path: $ArtifactRoot"
if ($generatedArtifactRoot -and -not $artifactRootWasProvided -and -not $KeepArtifactRoot -and (Test-Path -LiteralPath $ArtifactRoot)) {
  $tempRoot = [System.IO.Path]::GetTempPath()
  $resolvedArtifactRoot = (Resolve-Path -LiteralPath $ArtifactRoot).Path
  if (-not $resolvedArtifactRoot.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to clean generated artifact root outside temp: $resolvedArtifactRoot"
  }
  Remove-Item -LiteralPath $resolvedArtifactRoot -Recurse -Force
  Write-Host "ok: generated artifact root cleaned: $resolvedArtifactRoot"
}
exit 0

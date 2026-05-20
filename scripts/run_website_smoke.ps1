param(
  [string]$WebsiteRoot = "",
  [switch]$Build
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")

if (-not $WebsiteRoot) {
  $candidate = Resolve-Path -LiteralPath (Join-Path $RepoRoot "..\lexa-website") -ErrorAction SilentlyContinue
  if ($candidate) { $WebsiteRoot = $candidate.Path }
}

if (-not $WebsiteRoot -or !(Test-Path -LiteralPath $WebsiteRoot)) {
  Write-Warning "Website path not found. Website smoke skipped."
  exit 0
}

Write-Host "Website smoke"
Write-Host "WebsiteRoot: $WebsiteRoot"

$secretHits = @()
Get-ChildItem -LiteralPath $WebsiteRoot -Recurse -Force -File -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '[\\/]node_modules[\\/]' } |
  ForEach-Object {
    if ($_.Name -match '(^\.env|\.env$)' -or $_.Name -match '(?i)(secret|private).*\.key$') {
      $secretHits += $_.FullName
    }
  }
if ($secretHits.Count -gt 0) {
  throw "Potential website secret files found: $($secretHits -join ', ')"
}

$tmpFiles = @(Get-ChildItem -LiteralPath $WebsiteRoot -File -Filter "tmp_*.js" -ErrorAction SilentlyContinue)
if ($tmpFiles.Count -gt 0) {
  Write-Warning "Website has tmp_*.js scratch/migration files. Keep them out of product deployment unless reviewed: $($tmpFiles.Name -join ', ')"
}

$pkg = Join-Path $WebsiteRoot "package.json"
if (Test-Path -LiteralPath $pkg) {
  $package = Get-Content -LiteralPath $pkg -Raw | ConvertFrom-Json
  if ($Build -and $package.scripts.build) {
    Push-Location $WebsiteRoot
    try { npm.cmd run build } finally { Pop-Location }
  } else {
    Write-Host "Website package.json found. Build skipped unless -Build is supplied and a build script exists."
  }
} else {
  Write-Host "No website package.json found; treating website as static HTML/CSS/JS layer."
}

Write-Host "Website smoke completed without deployment or upload."
exit 0

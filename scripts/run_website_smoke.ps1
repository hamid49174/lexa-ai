param(
  [string]$WebsiteRoot = "",
  [switch]$Build,
  [ValidateSet("InternalRC", "PublicRC", "PublicRelease")]
  [string]$Target = "InternalRC"
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
Write-Host "Website release target: static-external"
Write-Host "Release target: $Target"

$secretHits = @()
$secretPatternHits = @()
$externalScripts = @()
Get-ChildItem -LiteralPath $WebsiteRoot -Recurse -Force -File -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '[\\/]node_modules[\\/]' } |
  ForEach-Object {
    if ($_.Name -match '(^\.env|\.env$)' -or $_.Name -match '(?i)(secret|private).*\.key$') {
      $secretHits += $_.FullName
    }
    if ($_.Extension -in @(".js", ".html", ".css")) {
      $text = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
      if ($text -match '(?i)(sk_live_|sk_test_|service_role|SUPABASE_SERVICE_ROLE|STRIPE_SECRET_KEY|api[_-]?key\s*[:=]\s*["''][A-Za-z0-9_\-]{20,})') {
        $secretPatternHits += $_.FullName
      }
      if ($_.Extension -eq ".html") {
        foreach ($match in [regex]::Matches($text, '<script[^>]+src=["'']([^"'']+)["'']')) {
          $src = $match.Groups[1].Value
          if ($src -match '^https?://') { $externalScripts += "$($_.Name): $src" }
        }
      }
    }
  }
if ($secretHits.Count -gt 0) {
  throw "Potential website secret files found: $($secretHits -join ', ')"
}
if ($secretPatternHits.Count -gt 0) {
  throw "Potential website secret patterns found: $($secretPatternHits -join ', ')"
}

$tmpFiles = @(Get-ChildItem -LiteralPath $WebsiteRoot -File -Filter "tmp_*.js" -ErrorAction SilentlyContinue)
if ($tmpFiles.Count -gt 0) {
  Write-Warning "Website has tmp_*.js scratch/migration files. Keep them out of product deployment unless reviewed: $($tmpFiles.Name -join ', ')"
}

$pkg = Join-Path $WebsiteRoot "package.json"
$config = Join-Path $WebsiteRoot "config.js"
if (Test-Path -LiteralPath $config) {
  $configText = Get-Content -LiteralPath $config -Raw
  if ($configText -match 'YOUR_PROJECT|YOUR_ANON_KEY|YOUR_KEY|YOUR_PORTAL_ID') {
    Write-Warning "Website config.js still contains placeholder Supabase/Stripe values. This is safe for smoke but not release-ready."
  }
  if ($configText -match 'pk_(live|test)_YOUR') {
    Write-Warning "Website Stripe publishable key is a placeholder. Real publishable keys are public, but secret keys must never be committed."
  }
}

if ($externalScripts.Count -gt 0) {
  Write-Warning "Website uses external scripts/CDN resources that need CSP/vendor review before release: $($externalScripts -join '; ')"
}

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
  Write-Warning "Website has no package-based build/lint proof. Treat as warn-only for InternalRC and blocking for PublicRC/PublicRelease until a release target is approved."
  if ($Target -in @("PublicRC", "PublicRelease")) {
    throw "Website static-external target without package-based build/lint proof blocks $Target."
  }
}

Write-Host "Website smoke completed without deployment or upload."
exit 0

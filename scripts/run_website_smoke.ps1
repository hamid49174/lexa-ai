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

$websiteRootPath = (Resolve-Path -LiteralPath $WebsiteRoot).Path
$pkg = Join-Path $WebsiteRoot "package.json"
$packageLock = Join-Path $WebsiteRoot "package-lock.json"
$npmShrinkwrap = Join-Path $WebsiteRoot "npm-shrinkwrap.json"
$yarnLock = Join-Path $WebsiteRoot "yarn.lock"
$pnpmLock = Join-Path $WebsiteRoot "pnpm-lock.yaml"
$packageSecretScanPaths = @($pkg, $packageLock, $npmShrinkwrap, $yarnLock, $pnpmLock)
$secretHits = @()
$secretPatternHits = @()
$websiteSecretScanPaths = New-Object System.Collections.Generic.List[string]
$externalScripts = @()
$unsupportedExternalScripts = @()
$externalResources = @()
$unsupportedExternalResources = @()
$allowedExternalScriptPatterns = @(
  '^https://js\.stripe\.com/v3/?$'
)
$allowedExternalResourcePatterns = @(
  '^https://unpkg\.com/@splinetool/runtime@1\.9\.82/build/runtime\.js$',
  '^https://prod\.spline\.design/kZDDjO5HuC9GJUM2/scene\.splinecode$'
)
$websiteSecretPathRegex = '(?i)(^|/)(\.netrc|\.npmrc|\.pnpmrc|\.pypirc|\.yarnrc(\.yml)?|pip\.(conf|ini)|(credentials|secrets)\.(json|ya?ml|toml|ini|conf)|client_secret[^/]*\.json|service[-_]?account[^/]*\.json)$|(^|/)\.aws/(credentials|config)$|(^|/)\.azure/(accessTokens|azureProfile)\.json$|(^|/)\.config/gcloud/application_default_credentials\.json$|(^|/)\.docker/config\.json$|(^|/)\.gcloud/application_default_credentials\.json$|(^|/)\.kube/config$|(^|/)\.ssh/(id_dsa|id_ecdsa|id_ed25519|id_rsa)$|(^|/)(id_dsa|id_ecdsa|id_ed25519|id_rsa)$|\.(pfx|p12|pem|ppk|key|pvk|cer|crt|spc|jks|keystore)$'
function Test-AllowedWebsiteExternal {
  param(
    [string]$Url,
    [string[]]$Patterns
  )
  foreach ($pattern in $Patterns) {
    if ($Url -match $pattern) {
      return $true
    }
  }
  return $false
}
function Invoke-RiskyWebsiteSecretScanPathCheck([string[]]$PathValues) {
  if (-not $PathValues -or $PathValues.Count -eq 0) { return }
  & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "check_risky_artifacts.ps1") -Root $RepoRoot -Mode Strict -SecretScanPath $PathValues
  if ($LASTEXITCODE -ne 0) {
    throw "Potential website secret patterns found by central risky-artifact scanner."
  }
}
$cspCriticalPages = @("auth.html", "dashboard.html")
Get-ChildItem -LiteralPath $WebsiteRoot -Recurse -Force -File -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '[\\/]node_modules[\\/]' } |
  ForEach-Object {
    $relative = $_.FullName.Substring($websiteRootPath.Length).TrimStart('\', '/') -replace '\\', '/'
    if ($_.Name -match '(^\.env|\.env$)' -or $_.Name -match '(?i)(secret|private).*\.key$' -or $relative -match $websiteSecretPathRegex) {
      $secretHits += $relative
    }
    if ($_.Extension -in @(".js", ".html", ".css")) {
      $websiteSecretScanPaths.Add($_.FullName) | Out-Null
      $text = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
      if ($text -match '(?i)(sk_live_|sk_test_|service_role|SUPABASE_SERVICE_ROLE|STRIPE_SECRET_KEY|api[_-]?key\s*[:=]\s*["''][A-Za-z0-9_\-]{20,})') {
        $secretPatternHits += $_.FullName
      }
      if ($_.Extension -eq ".html") {
        foreach ($match in [regex]::Matches($text, '<script[^>]+src=["'']([^"'']+)["'']')) {
          $src = $match.Groups[1].Value
          if ($src -match '^https?://') {
            $entry = "$($_.Name): $src"
            $externalScripts += $entry
            if (-not (Test-AllowedWebsiteExternal $src $allowedExternalScriptPatterns)) {
              $unsupportedExternalScripts += $entry
            }
          }
        }
        foreach ($linkMatch in [regex]::Matches($text, '<link\b[^>]*>', "IgnoreCase")) {
          $tag = $linkMatch.Value
          if ($tag -match '\brel=["''](?:modulepreload|preload)["'']') {
            $hrefMatch = [regex]::Match($tag, '\bhref=["'']([^"'']+)["'']', "IgnoreCase")
            if ($hrefMatch.Success) {
              $href = $hrefMatch.Groups[1].Value
              if ($href -match '^https?://') {
                $entry = "$($_.Name): $href"
                $externalResources += $entry
                if (-not (Test-AllowedWebsiteExternal $href $allowedExternalResourcePatterns)) {
                  $unsupportedExternalResources += $entry
                }
              }
            }
          }
        }
      }
      if ($_.Name -eq "landing-spline.js") {
        foreach ($match in [regex]::Matches($text, "https://[^'""\s)]+")) {
          $url = $match.Value
          $entry = "$($_.Name): $url"
          $externalResources += $entry
          if (-not (Test-AllowedWebsiteExternal $url $allowedExternalResourcePatterns)) {
            $unsupportedExternalResources += $entry
          }
        }
      }
    }
  }
Invoke-RiskyWebsiteSecretScanPathCheck @($websiteSecretScanPaths)
Invoke-RiskyWebsiteSecretScanPathCheck @($packageSecretScanPaths | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
if ($secretHits.Count -gt 0) {
  throw "Potential website secret files found: $($secretHits -join ', ')"
}
if ($secretPatternHits.Count -gt 0) {
  throw "Potential website secret patterns found: $($secretPatternHits -join ', ')"
}

foreach ($page in $cspCriticalPages) {
  $pagePath = Join-Path $WebsiteRoot $page
  if (!(Test-Path -LiteralPath $pagePath)) {
    throw "Website CSP page missing: $page"
  }
  $pageText = Get-Content -LiteralPath $pagePath -Raw
  $cspMatch = [regex]::Match($pageText, '<meta\s+http-equiv=["'']Content-Security-Policy["''][^>]*content="([^"]+)"', "IgnoreCase")
  if (-not $cspMatch.Success) {
    $cspMatch = [regex]::Match($pageText, "<meta\s+http-equiv=[""']Content-Security-Policy[""'][^>]*content='([^']+)'", "IgnoreCase")
  }
  if (-not $cspMatch.Success) {
    throw "Website $page is missing Content-Security-Policy meta tag."
  }
  $csp = $cspMatch.Groups[1].Value
  foreach ($requiredCsp in @(
    "script-src 'self' https://js.stripe.com",
    "style-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'"
  )) {
    if (-not $csp.Contains($requiredCsp)) {
      throw "Website $page CSP is missing: $requiredCsp"
    }
  }
  if ($csp -match "unsafe-inline" -or $pageText -match '\sstyle\s*=' -or $pageText -match '\son[a-z]+\s*=') {
    throw "Website $page contains inline style/event handlers or unsafe-inline CSP."
  }
}

Get-ChildItem -LiteralPath $WebsiteRoot -Recurse -Force -File -Filter "*.html" -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '[\\/]node_modules[\\/]' -and $_.FullName -notmatch '[\\/]dist[\\/]' } |
  ForEach-Object {
    $htmlText = Get-Content -LiteralPath $_.FullName -Raw
    if ($htmlText -match '<script\b(?![^>]*\bsrc=)[^>]*>' -or $htmlText -match '\sstyle\s*=' -or $htmlText -match '\son[a-z]+\s*=') {
      throw "Website HTML contains inline script/style/event handlers: $($_.Name)"
    }
  }

foreach ($accountScript in @("auth.js", "dashboard.js")) {
  $scriptPath = Join-Path $WebsiteRoot $accountScript
  if (!(Test-Path -LiteralPath $scriptPath)) {
    throw "Website account script missing: $accountScript"
  }
  $scriptText = Get-Content -LiteralPath $scriptPath -Raw
  if ($scriptText -match '\b(innerHTML|insertAdjacentHTML|outerHTML|document\.write)\b') {
    throw "Website $accountScript contains dynamic HTML sinks on account pages."
  }
  if ($scriptText -match '\bstyle\s*\.') {
    throw "Website $accountScript contains inline style mutations on account pages."
  }
}

$i18nPath = Join-Path $WebsiteRoot "i18n.js"
if (!(Test-Path -LiteralPath $i18nPath)) {
  throw "Website i18n.js missing."
}
$i18nText = Get-Content -LiteralPath $i18nPath -Raw
if ($i18nText -notmatch "setSafeI18nHtml" -or $i18nText -notmatch "appendSafeI18nNode" -or $i18nText -match 'el\.innerHTML\s*=') {
  throw "Website i18n.js must render formatted translations through the safe allowlist renderer."
}

$tmpFiles = @(Get-ChildItem -LiteralPath $WebsiteRoot -File -Filter "tmp_*.js" -ErrorAction SilentlyContinue)
if ($tmpFiles.Count -gt 0) {
  Write-Warning "Website has tmp_*.js scratch/migration files. Keep them out of product deployment unless reviewed: $($tmpFiles.Name -join ', ')"
}

function Invoke-NpmScript {
  param(
    [string]$ScriptName,
    [string]$Label
  )
  Push-Location $WebsiteRoot
  try {
    npm.cmd run $ScriptName
    if ($LASTEXITCODE -ne 0) {
      throw "$Label failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

function Get-JsStringConfigValue {
  param(
    [string]$Text,
    [string]$Key
  )
  $escapedKey = [regex]::Escape($Key)
  $match = [regex]::Match($Text, "$escapedKey\s*:\s*['""]([^'""]+)['""]")
  if ($match.Success) { return $match.Groups[1].Value.Trim() }
  return ""
}

function Test-DeployableWebsiteRuntimeConfig {
  param([string]$Text)
  $checks = @(
    @{ Key = "SUPABASE_URL"; Pattern = '^https://[a-z0-9-]+\.supabase\.co/?$' },
    @{ Key = "SUPABASE_ANON_KEY"; Pattern = '^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$' },
    @{ Key = "STRIPE_PUBLISHABLE_KEY"; Pattern = '^pk_(live|test)_[A-Za-z0-9_=-]{10,}$' },
    @{ Key = "APP_URL"; Pattern = '^https://[^/\s]+' },
    @{ Key = "API_URL"; Pattern = '^https://[^/\s]+' },
    @{ Key = "pro_monthly"; Pattern = '^price_[A-Za-z0-9_]{8,}$' },
    @{ Key = "pro_yearly"; Pattern = '^price_[A-Za-z0-9_]{8,}$' },
    @{ Key = "ultra_monthly"; Pattern = '^price_[A-Za-z0-9_]{8,}$' },
    @{ Key = "ultra_yearly"; Pattern = '^price_[A-Za-z0-9_]{8,}$' }
  )
  $missing = @()
  foreach ($check in $checks) {
    $value = Get-JsStringConfigValue $Text $check.Key
    if (-not $value -or $value -notmatch $check.Pattern) {
      $missing += $check.Key
    }
  }
  return $missing
}

$config = Join-Path $WebsiteRoot "config.js"
$runtimeConfig = Join-Path $WebsiteRoot "config.runtime.js"
if (Test-Path -LiteralPath $config) {
  $configText = Get-Content -LiteralPath $config -Raw
  $runtimeConfigExists = Test-Path -LiteralPath $runtimeConfig
  $runtimeConfigText = if ($runtimeConfigExists) { Get-Content -LiteralPath $runtimeConfig -Raw } else { "" }
  $deploymentConfigText = if ($runtimeConfigText) { $runtimeConfigText } else { $configText }
  if ($deploymentConfigText -match 'YOUR_PROJECT|YOUR_ANON_KEY|YOUR_KEY|YOUR_PORTAL_ID|price_(PRO|ULTRA)_[A-Z_]*ID') {
    $configSource = if ($runtimeConfigText) { "config.runtime.js" } else { "config.js" }
    Write-Warning "Website $configSource still contains placeholder Supabase/Stripe values. This is safe for smoke but not release-ready."
    if ($Target -in @("PublicRC", "PublicRelease")) {
      throw "Website config placeholders block $Target. Create config.runtime.js from config.runtime.example.js with real public values."
    }
  }
  if ($deploymentConfigText -match 'pk_(live|test)_YOUR') {
    Write-Warning "Website Stripe publishable key is a placeholder. Real publishable keys are public, but secret keys must never be committed."
    if ($Target -in @("PublicRC", "PublicRelease")) {
      throw "Website Stripe publishable key placeholder blocks $Target. Use config.runtime.js for real public values."
    }
  }
  if ($runtimeConfigExists) {
    $runtimeConfigMissing = @(Test-DeployableWebsiteRuntimeConfig $runtimeConfigText)
    if ($runtimeConfigMissing.Count -gt 0) {
      $message = "Website config.runtime.js is missing deployable public values: $($runtimeConfigMissing -join ', ')"
      Write-Warning $message
      if ($Target -in @("PublicRC", "PublicRelease")) {
        throw "$message. Replace placeholders before $Target."
      }
    }
  }
}

if ($unsupportedExternalScripts.Count -gt 0) {
  Write-Warning "Website uses unsupported external scripts/CDN resources that need CSP/vendor review before release: $($unsupportedExternalScripts -join '; ')"
  if ($Target -in @("PublicRC", "PublicRelease")) {
    throw "Website unsupported external scripts block $Target."
  }
}
if ($unsupportedExternalResources.Count -gt 0) {
  Write-Warning "Website uses unsupported external preload/module resources that need CSP/vendor review before release: $($unsupportedExternalResources -join '; ')"
  if ($Target -in @("PublicRC", "PublicRelease")) {
    throw "Website unsupported external resources block $Target."
  }
}
if ($externalScripts.Count -gt 0 -and $unsupportedExternalScripts.Count -eq 0) {
  Write-Host "ok: external scripts are allowlisted: $($externalScripts -join '; ')"
}
if ($externalResources.Count -gt 0 -and $unsupportedExternalResources.Count -eq 0) {
  Write-Host "ok: external preload/module resources are allowlisted: $($externalResources -join '; ')"
}

if (Test-Path -LiteralPath $pkg) {
  $package = Get-Content -LiteralPath $pkg -Raw | ConvertFrom-Json
  $scriptNames = @()
  if ($package.scripts) {
    $scriptNames = @($package.scripts.PSObject.Properties.Name)
  }
  if ($scriptNames -contains "lint") {
    Invoke-NpmScript "lint" "Website lint"
  } else {
    Write-Warning "Website package.json has no lint script."
    if ($Target -in @("PublicRC", "PublicRelease")) {
      throw "Website package without lint script blocks $Target."
    }
  }
  if ($Build -and ($scriptNames -contains "build")) {
    Invoke-NpmScript "build" "Website build"
  } elseif ($Build) {
    Write-Warning "Website package.json has no build script."
    if ($Target -in @("PublicRC", "PublicRelease")) {
      throw "Website package without build script blocks $Target."
    }
  } else {
    Write-Host "Website package.json found. Build skipped unless -Build is supplied."
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

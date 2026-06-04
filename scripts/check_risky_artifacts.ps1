param(
  [string]$Root = "",
  [ValidateSet("Warn", "Strict")]
  [string]$Mode = "Strict",
  [string]$StagedFileList = "",
  [string[]]$ArtifactPath = @(),
  [string[]]$SecretScanPath = @()
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
  $Root = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
} else {
  $Root = Resolve-Path -LiteralPath $Root
}

Set-Location $Root

$riskPatterns = @(
  '^personal_os(/|$)',
  '^tmp(/|$)',
  '^vendor(/|$)',
  '^audit\.log$',
  '^bridge-audit\.log$',
  '^lexa_memory\.db($|-)',
  '^hermes_workspace(/|$)',
  '(^|/)\.env($|\.|/)',
  '\.env$',
  '(^|/)\.netrc$',
  '(^|/)\.npmrc$',
  '(^|/)\.pnpmrc$',
  '(^|/)\.pypirc$',
  '(^|/)\.yarnrc(\.yml)?$',
  '(^|/)\.aws/(credentials|config)$',
  '(^|/)\.azure/(accessTokens|azureProfile)\.json$',
  '(^|/)\.config/gcloud/application_default_credentials\.json$',
  '(^|/)\.docker/config\.json$',
  '(^|/)\.gcloud/application_default_credentials\.json$',
  '(^|/)\.kube/config$',
  '(^|/)(credentials|secrets)\.(json|ya?ml|toml|ini|conf)$',
  '(^|/)client_secret[^/]*\.json$',
  '(^|/)service[-_]?account[^/]*\.json$',
  '(^|/)\.ssh/(id_dsa|id_ecdsa|id_ed25519|id_rsa)$',
  '(^|/)(id_dsa|id_ecdsa|id_ed25519|id_rsa)$',
  '(^|/)pip\.(conf|ini)$',
  '^evals/results/.+\.(json|md|html|jsonl)$',
  '^evals/results/traces/',
  '^tmp/agent_traces/',
  '^dist(/|$)',
  '^dist-[^/]*build(/|$)',
  '^backend-dist(/|$)',
  '^frontend/dist(/|$)',
  '^build(/|$)',
  '^\.pytest_cache(/|$)',
  '^\.coverage$',
  '^audio_cache(/|$)',
  '(^|/)node_modules(/|$)',
  '^venv(/|$)',
  '\.(pfx|p12|pem|ppk|key|pvk|cer|crt|spc|jks|keystore)$',
  '(^|/)(codesign|code-sign|signing|signtool)[^/]*\.(json|ps1|env|txt|xml)$',
  '(^|/)(windows|electron)[_-]?(signing|certificate|cert)[^/]*\.(json|ps1|env|txt|xml)$'
)

$secretRegex = '(?i)(api[_-]?key|access[_-]?key|service[_-]?role[_-]?key|bearer|token|credential|secret|password|passphrase|passwd|private[_-]?key|csc[_-]key[_-]?password|csc[_-]link|win[_-]csc[_-]link|signing[_-]?password|signtool[_-]?password)\s*[:=]\s*["'']?[^\s"'']{8,}'
$structuredSecretRegex = '(?i)["'']?[^"''\r\n:=]*(api[_-]?key|access[_-]?key|service[_-]?role[_-]?key|bearer|token|credential|secret|password|passphrase|passwd|private[_-]?key|csc[_-]key[_-]?password|csc[_-]link|win[_-]csc[_-]link|signing[_-]?password|signtool[_-]?password)["'']?\s*[:=]\s*(["''][^"''\r\n]{8,}["'']|[^\s"'',}\]]{8,})'
$quotedSecretRegex = '(?i)(api[_-]?key|access[_-]?key|service[_-]?role[_-]?key|bearer|token|credential|secret|password|passphrase|passwd|private[_-]?key|csc[_-]key[_-]?password|csc[_-]link|win[_-]csc[_-]link|signing[_-]?password|signtool[_-]?password)\s*[:=]\s*["''][^"''\r\n]{8,}["'']'
$signtoolSecretRegex = '(?i)signtool(\.exe)?\s+sign[^\r\n]*(\s/p\s+|\s/pass\s+|\s/password\s+)["'']?[^"''\s]+'
$cliSecretRegex = '(?i)(^|[\s"''])(--?(api[_-]?key|access[_-]?key|service[_-]?role[_-]?key|token|credential|secret|password|passphrase|passwd|private[_-]?key)|/(token|credential|secret|password|passphrase|passwd))(\s+|=)(["''][^"''\r\n]{8,}["'']|[^\s"'']{8,})'
$urlCredentialRegex = '(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]{2,}:[^/\s@]{8,}@'
$bearerSecretRegex = '(?i)\bAuthorization\s*:\s*Bearer\s+["'']?[A-Za-z0-9_\-\.\/\\:;+=]{12,}'
$privateKeyBlockRegex = '(?i)-----BEGIN (RSA |DSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'
$providerTokenRegex = '(?i)\b(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|npm_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|gsk_[A-Za-z0-9_]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|sk-or-v1-[A-Za-z0-9_-]{20,}|sk_car_[A-Za-z0-9_-]{16,}|sk-(proj|svcacct)-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,}|sk_(live|test)_[A-Za-z0-9]{16,})\b'
$lexaLicenseKeyRegex = '(?i)\bLEXA-(?!00000-00000-00000-00000\b)[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}\b'
$envExampleSecretNameRegex = '(?i)(^|_)(api[_-]?key|access[_-]?key|service[_-]?role[_-]?key|secret|token|credential|password|passphrase|passwd|private[_-]?key|webhook|dsn)($|_)'
$envExamplePlaceholderValueRegex = '(?i)^(\s*|your[_-].*|.*your[_-].*|.*placeholder.*|.*example.*|.*sample.*|.*dummy.*|.*fake.*|.*test.*|.*dev(elopment)?.*|.*local.*|changeme|change[_-]?me|replace[_-]?me|redacted|none|null|todo|x{4,}|0{4,}|<[^>]+>)$'
$violations = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

function Normalize-RepoPath {
  param([string]$PathValue)
  $normalized = $PathValue -replace '\\', '/'
  if ($normalized.StartsWith("./")) { $normalized = $normalized.Substring(2) }
  return $normalized.TrimStart('/')
}

function Test-RiskyPath {
  param([string]$PathValue)
  $normalized = Normalize-RepoPath $PathValue
  if ($normalized -match '(^|/)\.env\.example$') { return $false }
  foreach ($pattern in $riskPatterns) {
    if ($normalized -match $pattern) { return $true }
  }
  return $false
}

function Test-AllowedArtifactPath {
  param([string]$PathValue)
  $normalized = Normalize-RepoPath $PathValue
  return $normalized -match '(^|/)(resources/backend-dist/)?_internal/certifi/cacert\.pem$'
}

function Test-StrongSecretLikeText {
  param([string]$Text)
  if (-not $Text) { return $false }
  return (
    $Text -match $providerTokenRegex -or
    $Text -match $lexaLicenseKeyRegex -or
    $Text -match $bearerSecretRegex -or
    $Text -match $privateKeyBlockRegex -or
    $Text -match $signtoolSecretRegex -or
    $Text -match $cliSecretRegex -or
    (Test-EnvExampleSecretLikeText $Text)
  )
}

function Test-EnvExampleSecretLikeText {
  param([string]$Text)
  if (-not $Text) { return $false }

  foreach ($line in ([regex]::Split($Text, '\r?\n'))) {
    $candidate = $line.Trim()
    if (-not $candidate) { continue }
    if ($candidate.StartsWith("#")) { $candidate = $candidate.Substring(1).TrimStart() }
    if (-not $candidate -or $candidate.StartsWith("#")) { continue }
    if ($candidate -notmatch '^\s*(?:(?:export|set)\s+|\$env:)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { continue }

    $name = $matches[1]
    $value = $matches[2].Trim()
    if ($name -notmatch $envExampleSecretNameRegex) { continue }
    if (-not $value) { continue }

    $quote = $value.Substring(0, 1)
    if ($quote -eq '"' -or $quote -eq "'") {
      $value = $value.Substring(1)
      $quoteEnd = $value.IndexOf($quote)
      if ($quoteEnd -ge 0) { $value = $value.Substring(0, $quoteEnd) }
    } else {
      $value = ($value -replace '\s+#.*$', '').Trim()
    }

    if (-not $value) { continue }
    if ($value -match $envExamplePlaceholderValueRegex) { continue }
    if ($value.Length -ge 8) { return $true }
  }

  return $false
}

function Add-Finding {
  param([string]$Message, [bool]$Blocking = $true)
  if ($Blocking -and $Mode -eq "Strict") { $violations.Add($Message) | Out-Null }
  else { $warnings.Add($Message) | Out-Null }
}

function Get-StagedFiles {
  if ($StagedFileList) {
    if (!(Test-Path -LiteralPath $StagedFileList)) { throw "Staged file list not found: $StagedFileList" }
    return Get-Content -LiteralPath $StagedFileList | Where-Object { $_ -and $_.Trim() }
  }

  if (Test-Path -LiteralPath (Join-Path $Root ".git")) {
    return @(git diff --cached --name-only)
  }

  return @()
}

function Get-StagedOrWorkingTreeText {
  param([string]$PathValue)
  $normalized = Normalize-RepoPath $PathValue

  if (-not $StagedFileList -and (Test-Path -LiteralPath (Join-Path $Root ".git"))) {
    $stagedText = @(git show ":$normalized" 2>$null)
    if ($LASTEXITCODE -eq 0) {
      return ($stagedText -join [Environment]::NewLine)
    }
  }

  $worktreePath = Join-Path $Root ($normalized -replace '/', [System.IO.Path]::DirectorySeparatorChar)
  if (Test-Path -LiteralPath $worktreePath) {
    return Get-Content -LiteralPath $worktreePath -Raw -ErrorAction SilentlyContinue
  }

  return $null
}

$stagedFiles = @(Get-StagedFiles)
foreach ($file in $stagedFiles) {
  $normalizedFile = Normalize-RepoPath $file
  if ($normalizedFile -match '(^|/)\.env\.example$') {
    $envExampleText = Get-StagedOrWorkingTreeText $normalizedFile
    if (Test-StrongSecretLikeText $envExampleText) {
      Add-Finding "Secret-like value found in staged env placeholder file: $file" $true
    }
  }
  if (Test-RiskyPath $file) {
    Add-Finding "Risky staged path: $file" $true
  }
}

if (Test-Path -LiteralPath (Join-Path $Root ".git")) {
  $riskyStatusArgs = @("status", "--short", "--",
    "personal_os", "tmp", "vendor", "audit.log", "bridge-audit.log",
    "lexa_memory.db", "lexa_memory.db-*", "hermes_workspace",
    "evals/results", "dist", "dist-*-build", "backend-dist", "frontend/dist", "build",
    ".netrc", ".npmrc", ".pnpmrc", ".pypirc", ".yarnrc", ".yarnrc.yml",
    ".aws/credentials", ".aws/config", ".azure/accessTokens.json", ".azure/azureProfile.json",
    ".config/gcloud/application_default_credentials.json", ".docker/config.json",
    ".gcloud/application_default_credentials.json", ".kube/config",
    "credentials.json", "credentials.yml", "credentials.yaml", "credentials.toml", "credentials.ini", "credentials.conf",
    "secrets.json", "secrets.yml", "secrets.yaml", "secrets.toml", "secrets.ini", "secrets.conf",
    "client_secret.json", "service-account.json", "service_account.json",
    ".ssh/id_dsa", ".ssh/id_ecdsa", ".ssh/id_ed25519", ".ssh/id_rsa",
    "*.ppk", "pip.conf", "pip.ini",
    ":(glob)**/.netrc", ":(glob)**/.npmrc", ":(glob)**/.pnpmrc", ":(glob)**/.pypirc",
    ":(glob)**/.yarnrc", ":(glob)**/.yarnrc.yml",
    ":(glob)**/.aws/credentials", ":(glob)**/.aws/config",
    ":(glob)**/.azure/accessTokens.json", ":(glob)**/.azure/azureProfile.json",
    ":(glob)**/.config/gcloud/application_default_credentials.json",
    ":(glob)**/.docker/config.json", ":(glob)**/.gcloud/application_default_credentials.json",
    ":(glob)**/.kube/config",
    ":(glob)**/credentials.json", ":(glob)**/credentials.yml", ":(glob)**/credentials.yaml",
    ":(glob)**/credentials.toml", ":(glob)**/credentials.ini", ":(glob)**/credentials.conf",
    ":(glob)**/secrets.json", ":(glob)**/secrets.yml", ":(glob)**/secrets.yaml",
    ":(glob)**/secrets.toml", ":(glob)**/secrets.ini", ":(glob)**/secrets.conf",
    ":(glob)**/client_secret*.json", ":(glob)**/service-account*.json",
    ":(glob)**/service_account*.json",
    ":(glob)**/.ssh/id_dsa", ":(glob)**/.ssh/id_ecdsa",
    ":(glob)**/.ssh/id_ed25519", ":(glob)**/.ssh/id_rsa",
    ":(glob)**/id_dsa", ":(glob)**/id_ecdsa", ":(glob)**/id_ed25519", ":(glob)**/id_rsa",
    ":(glob)**/pip.conf", ":(glob)**/pip.ini",
    ":(glob)**/*.pfx", ":(glob)**/*.p12", ":(glob)**/*.pem", ":(glob)**/*.ppk",
    ":(glob)**/*.key", ":(glob)**/*.pvk", ":(glob)**/*.cer", ":(glob)**/*.crt",
    ":(glob)**/*.spc", ":(glob)**/*.jks", ":(glob)**/*.keystore"
  )
  $riskStatus = @(git @riskyStatusArgs)
  foreach ($row in $riskStatus) {
    Add-Finding "Risky local path present (not staged check): $row" $false
  }
}

foreach ($artifact in $ArtifactPath) {
  if (-not $artifact) { continue }
  $resolvedArtifact = $null
  try { $resolvedArtifact = Resolve-Path -LiteralPath $artifact -ErrorAction Stop } catch { continue }
  $artifactRoot = $resolvedArtifact.Path
  $artifactItem = Get-Item -LiteralPath $artifactRoot -ErrorAction SilentlyContinue
  if (-not $artifactItem) { continue }
  $artifactItems = if ($artifactItem.PSIsContainer) {
    Get-ChildItem -LiteralPath $artifactRoot -Recurse -Force -File -ErrorAction SilentlyContinue
  } else {
    @($artifactItem)
  }
  $artifactItems | ForEach-Object {
    $relative = if ($artifactItem.PSIsContainer) {
      $_.FullName.Substring($artifactRoot.Length).TrimStart('\', '/')
    } else {
      Normalize-RepoPath $_.FullName
    }
    $contextualPath = Normalize-RepoPath $_.FullName
    $displayPath = $relative
    $isRiskyPath = Test-RiskyPath $relative
    if (-not $isRiskyPath -and (Test-RiskyPath $contextualPath)) {
      $isRiskyPath = $true
      $displayPath = $contextualPath
    }
    $isAllowedArtifactPath = (Test-AllowedArtifactPath $relative) -or (Test-AllowedArtifactPath $contextualPath)
    if ((-not $isAllowedArtifactPath) -and ($isRiskyPath -or $_.Name -match '(?i)^(\.env|audit\.log|bridge-audit\.log|lexa_memory\.db|lexa_memory\.db-|.*\.env$)')) {
      Add-Finding "Forbidden file in artifact path '$artifactRoot': $displayPath" $true
    }
  }
}

foreach ($scanPath in $SecretScanPath) {
  if (-not $scanPath -or !(Test-Path -LiteralPath $scanPath)) { continue }
  $items = if ((Get-Item -LiteralPath $scanPath).PSIsContainer) {
    Get-ChildItem -LiteralPath $scanPath -Recurse -Force -File
  } else {
    @(Get-Item -LiteralPath $scanPath)
  }
  foreach ($item in $items) {
    $text = Get-Content -LiteralPath $item.FullName -Raw -ErrorAction SilentlyContinue
    if ($text -match $secretRegex -or $text -match $structuredSecretRegex -or $text -match $quotedSecretRegex -or $text -match $signtoolSecretRegex -or $text -match $cliSecretRegex -or $text -match $urlCredentialRegex -or $text -match $bearerSecretRegex -or $text -match $privateKeyBlockRegex -or $text -match $providerTokenRegex -or $text -match $lexaLicenseKeyRegex) {
      Add-Finding "Secret-like pattern found in $($item.FullName)" $true
    }
  }
}

foreach ($warning in $warnings) {
  Write-Warning $warning
}

if ($violations.Count -gt 0) {
  $violations | ForEach-Object { Write-Error $_ }
  exit 1
}

$resultLabel = "passed"
if ($warnings.Count -gt 0) { $resultLabel = "completed with warnings" }

Write-Host "Risky artifact check $resultLabel. Staged files checked: $($stagedFiles.Count). Warnings: $($warnings.Count). Mode: $Mode."
exit 0

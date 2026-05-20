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
  '^evals/results/.+\.(json|md|html|jsonl)$',
  '^evals/results/traces/',
  '^tmp/agent_traces/',
  '^dist(/|$)',
  '^backend-dist(/|$)',
  '^frontend/dist(/|$)',
  '^build(/|$)',
  '^\.pytest_cache(/|$)',
  '^\.coverage$',
  '^audio_cache(/|$)',
  '(^|/)node_modules(/|$)',
  '^venv(/|$)',
  '\.(pfx|p12|pem|key)$',
  '(^|/)(codesign|code-sign|signing)[^/]*\.(json|ps1|env|txt)$'
)

$secretRegex = '(?i)(api[_-]?key|bearer|token|secret|private[_-]?key)\s*[:=]\s*["'']?[A-Za-z0-9_\-]{16,}'
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
  foreach ($pattern in $riskPatterns) {
    if ($normalized -match $pattern) { return $true }
  }
  return $false
}

function Add-Finding {
  param([string]$Message, [bool]$Blocking = $true)
  if ($Blocking) { $violations.Add($Message) | Out-Null }
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

$stagedFiles = @(Get-StagedFiles)
foreach ($file in $stagedFiles) {
  if (Test-RiskyPath $file) {
    Add-Finding "Risky staged path: $file" $true
  }
}

if (Test-Path -LiteralPath (Join-Path $Root ".git")) {
  $riskyStatusArgs = @("status", "--short", "--",
    "personal_os", "tmp", "vendor", "audit.log", "bridge-audit.log",
    "lexa_memory.db", "lexa_memory.db-*", "hermes_workspace",
    "evals/results", "dist", "backend-dist", "frontend/dist", "build"
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
  Get-ChildItem -LiteralPath $artifactRoot -Recurse -Force -File -ErrorAction SilentlyContinue | ForEach-Object {
    $relative = $_.FullName.Substring($artifactRoot.Length).TrimStart('\', '/')
    if (Test-RiskyPath $relative -or $_.Name -match '(?i)^(\.env|audit\.log|bridge-audit\.log|lexa_memory\.db|lexa_memory\.db-|.*\.env$)') {
      Add-Finding "Forbidden file in artifact path '$artifactRoot': $relative" $true
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
    if ($text -match $secretRegex) {
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

Write-Host "Risky artifact check passed. Staged files checked: $($stagedFiles.Count). Warnings: $($warnings.Count). Mode: $Mode."
exit 0

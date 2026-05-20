param(
  [string]$RepoRoot = "",
  [string]$CloneRoot = "",
  [switch]$DryRun,
  [switch]$Install,
  [switch]$RunQuickGate
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
} else {
  $RepoRoot = Resolve-Path -LiteralPath $RepoRoot
}

if (-not $CloneRoot) {
  $CloneRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("lexa-clean-clone-smoke-" + [guid]::NewGuid().ToString("N"))
}

$riskyPathRegex = '(?i)^(personal_os/|tmp/|vendor/|hermes_workspace/|evals/results/.+\.(json|md|html|jsonl)$|evals/results/traces/|dist/|backend-dist/|frontend/dist/|build/|\.pytest_cache/|audio_cache/|venv/|node_modules/|audit\.log$|bridge-audit\.log$|lexa_memory\.db($|-)|\.env$|.*\.env$)'
$riskDocumentation = @("personal_os/", "tmp/", "vendor/", "hermes_workspace/", "lexa_memory.db", "audit.log", "bridge-audit.log", "evals/results/*.json")

function Convert-ToRepoPath([string]$PathValue) {
  return ($PathValue -replace '\\', '/').TrimStart('./')
}

Write-Host "Lexa clean clone/copy smoke"
Write-Host "RepoRoot: $RepoRoot"
Write-Host "CloneRoot: $CloneRoot"
Write-Host "DryRun: $DryRun Install: $Install RunQuickGate: $RunQuickGate"

if (!(Test-Path -LiteralPath (Join-Path $RepoRoot ".git"))) {
  throw "RepoRoot is not a git repository: $RepoRoot"
}

$files = @(git -C $RepoRoot ls-files --cached --modified --others --exclude-standard)
if ($files.Count -eq 0) {
  throw "No source files found through git ls-files."
}

$risky = @($files | ForEach-Object { Convert-ToRepoPath $_ } | Where-Object { $_ -match $riskyPathRegex })
if ($risky.Count -gt 0) {
  throw "Clean clone source list contains risky paths: $($risky -join ', ')"
}

if ($DryRun) {
  Write-Host "Dry-run passed. Source file count: $($files.Count). No clean copy was written."
  exit 0
}

if (Test-Path -LiteralPath $CloneRoot) {
  throw "CloneRoot already exists. Choose an empty path: $CloneRoot"
}
New-Item -ItemType Directory -Path $CloneRoot | Out-Null

foreach ($file in $files) {
  $repoPath = Convert-ToRepoPath $file
  $source = Join-Path $RepoRoot $repoPath
  if (!(Test-Path -LiteralPath $source -PathType Leaf)) { continue }
  $target = Join-Path $CloneRoot $repoPath
  $targetDir = Split-Path -Parent $target
  if ($targetDir -and !(Test-Path -LiteralPath $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
  }
  Copy-Item -LiteralPath $source -Destination $target
}

$required = @(
  "requirements.txt",
  "frontend/package.json",
  "scripts/run_quality_gates.ps1",
  "scripts/run_eval_regression_gate.ps1",
  "scripts/run_release_candidate_check.ps1"
)
foreach ($rel in $required) {
  if (!(Test-Path -LiteralPath (Join-Path $CloneRoot $rel))) {
    throw "Required clean-copy file missing: $rel"
  }
}

$copiedRisky = @()
Get-ChildItem -LiteralPath $CloneRoot -Recurse -Force -File -ErrorAction SilentlyContinue | ForEach-Object {
  $relative = $_.FullName.Substring((Resolve-Path -LiteralPath $CloneRoot).Path.Length).TrimStart('\', '/') -replace '\\', '/'
  if ($relative -match $riskyPathRegex) { $copiedRisky += $relative }
}
if ($copiedRisky.Count -gt 0) {
  throw "Risky files found in clean copy: $($copiedRisky -join ', ')"
}

if ($Install) {
  Push-Location $CloneRoot
  try {
    python -m venv venv
    .\venv\Scripts\python.exe -m pip install --upgrade pip
    .\venv\Scripts\python.exe -m pip install -r requirements.txt
    if (Test-Path -LiteralPath "requirements-dev.txt") {
      .\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    }
    npm.cmd ci --prefix frontend
  } finally {
    Pop-Location
  }
} else {
  Write-Host "Install skipped. Use -Install for venv/npm dependency installation."
}

if ($RunQuickGate) {
  if (-not $Install) {
    throw "RunQuickGate requires -Install so the clean copy has dependencies."
  }
  Push-Location $CloneRoot
  try {
    powershell -ExecutionPolicy Bypass -File "scripts\run_quality_gates.ps1" -Mode Quick
  } finally {
    Pop-Location
  }
}

Write-Host "Clean clone/copy smoke completed. Clean copy path: $CloneRoot"
exit 0

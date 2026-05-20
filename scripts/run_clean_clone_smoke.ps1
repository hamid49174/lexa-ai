param(
  [string]$RepoRoot = "",
  [string]$CloneRoot = "",
  [switch]$DryRun,
  [switch]$Install,
  [switch]$RunQuickGate,
  [switch]$KeepTemp,
  [switch]$NoInstall
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

$riskyPathRegex = '(?i)^(personal_os/|tmp/|vendor/|hermes_workspace/|evals/results/.+\.(json|md|html|jsonl)$|evals/results/traces/|dist/|backend-dist/|frontend/dist/|frontend/node_modules/|build/|\.pytest_cache/|audio_cache/|venv/|node_modules/|audit\.log$|bridge-audit\.log$|lexa_memory\.db($|-)|\.env$|.*\.env$)'
$riskDocumentation = @("personal_os/", "tmp/", "vendor/", "hermes_workspace/", "lexa_memory.db", "audit.log", "bridge-audit.log", "evals/results/*.json")

function Convert-ToRepoPath([string]$PathValue) {
  $normalized = $PathValue -replace '\\', '/'
  if ($normalized.StartsWith("./")) { $normalized = $normalized.Substring(2) }
  return $normalized.TrimStart('/')
}

function Resolve-PythonForVenv {
  if ($env:LEXA_PYTHON -and (Test-Path -LiteralPath $env:LEXA_PYTHON)) {
    return [pscustomobject]@{ Command = $env:LEXA_PYTHON; Args = @() }
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return [pscustomobject]@{ Command = $python.Source; Args = @() }
  }
  $repoPython = Join-Path $RepoRoot "venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $repoPython) {
    return [pscustomobject]@{ Command = $repoPython; Args = @() }
  }
  $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
  if ($pyLauncher) {
    return [pscustomobject]@{ Command = $pyLauncher.Source; Args = @("-3") }
  }
  throw "No Python executable found for clean install. Set LEXA_PYTHON or install Python on PATH."
}

function Invoke-PythonCommand {
  param(
    [pscustomobject]$Invoker,
    [string[]]$Arguments
  )
  & $Invoker.Command @($Invoker.Args + $Arguments)
  if ($LASTEXITCODE -ne 0) {
    throw "Python command failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
  }
}

function Get-SourceFileList {
  if (Test-Path -LiteralPath (Join-Path $RepoRoot ".git")) {
    return @(git -C $RepoRoot ls-files --cached --modified --others --exclude-standard)
  }

  Write-Warning "RepoRoot has no .git directory; using source-only file scan for clean install workspace."
  $rootPath = (Resolve-Path -LiteralPath $RepoRoot).Path
  $expectedInstallArtifactRegex = '(?i)^(venv/|frontend/node_modules/|node_modules/)'
  $warnOnlyLocalArtifactRegex = '(?i)^(audio_cache/|hermes_workspace/|audit\.log$|bridge-audit\.log$|lexa_memory\.db($|-)|\.pytest_cache/|evals/results/|tmp/agent_traces/)'
  $allFiles = New-Object System.Collections.Generic.List[string]
  $blockingRisky = New-Object System.Collections.Generic.List[string]
  $warnOnlyRisky = New-Object System.Collections.Generic.List[string]
  $stack = New-Object System.Collections.Stack
  $stack.Push((Get-Item -LiteralPath $RepoRoot))
  while ($stack.Count -gt 0) {
    $dir = [System.IO.DirectoryInfo]$stack.Pop()
    Get-ChildItem -LiteralPath $dir.FullName -Force -Directory -ErrorAction SilentlyContinue | ForEach-Object {
      $relativeDir = ($_.FullName.Substring($rootPath.Length).TrimStart('\', '/') -replace '\\', '/') + "/"
      if ($relativeDir -match $riskyPathRegex) {
        if ($relativeDir -match $expectedInstallArtifactRegex -or $relativeDir -match $warnOnlyLocalArtifactRegex) {
          $warnOnlyRisky.Add($relativeDir) | Out-Null
        } else {
          $blockingRisky.Add($relativeDir) | Out-Null
        }
      } else {
        $stack.Push($_)
      }
    }
    Get-ChildItem -LiteralPath $dir.FullName -Force -File -ErrorAction SilentlyContinue | ForEach-Object {
      $relativeFile = $_.FullName.Substring($rootPath.Length).TrimStart('\', '/') -replace '\\', '/'
      $allFiles.Add($relativeFile) | Out-Null
    }
  }
  $fileRisky = @($allFiles | Where-Object { $_ -match $riskyPathRegex -and $_ -notmatch $expectedInstallArtifactRegex })
  foreach ($item in $fileRisky) {
    if ($item -match $warnOnlyLocalArtifactRegex) { $warnOnlyRisky.Add($item) | Out-Null }
    else { $blockingRisky.Add($item) | Out-Null }
  }
  if ($warnOnlyRisky.Count -gt 0) {
    Write-Warning "Source-only workspace has local generated artifacts that are excluded from the source list: $($warnOnlyRisky -join ', ')"
  }
  if ($blockingRisky.Count -gt 0) {
    throw "Source-only workspace contains risky paths: $($blockingRisky -join ', ')"
  }
  return @($allFiles | Where-Object { $_ -notmatch $riskyPathRegex })
}

Write-Host "Lexa clean clone/copy smoke"
Write-Host "RepoRoot: $RepoRoot"
Write-Host "CloneRoot: $CloneRoot"
Write-Host "DryRun: $DryRun Install: $Install RunQuickGate: $RunQuickGate KeepTemp: $KeepTemp NoInstall: $NoInstall"

if ($NoInstall) {
  $Install = $false
  if ($RunQuickGate) { throw "-RunQuickGate requires -Install and cannot be combined with -NoInstall." }
}

$files = @(Get-SourceFileList)
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
    $pythonForVenv = Resolve-PythonForVenv
    Invoke-PythonCommand $pythonForVenv @("-m", "venv", "venv")
    .\venv\Scripts\python.exe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed with exit code $LASTEXITCODE" }
    .\venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "requirements install failed with exit code $LASTEXITCODE" }
    if (Test-Path -LiteralPath "requirements-dev.txt") {
      .\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
      if ($LASTEXITCODE -ne 0) { throw "requirements-dev install failed with exit code $LASTEXITCODE" }
    }
    if (Test-Path -LiteralPath "frontend\package-lock.json") {
      npm.cmd ci --prefix frontend
      if ($LASTEXITCODE -ne 0) { throw "frontend npm ci failed with exit code $LASTEXITCODE" }
    } elseif (Test-Path -LiteralPath "frontend\package.json") {
      Write-Warning "frontend/package.json exists without package-lock.json; npm install is not run by clean smoke."
    }
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

if ($KeepTemp) {
  Write-Host "KeepTemp requested. Clean copy retained at: $CloneRoot"
} else {
  Write-Host "Clean copy retained for inspection at: $CloneRoot"
}
Write-Host "Clean clone/copy smoke completed. Clean copy path: $CloneRoot"
exit 0

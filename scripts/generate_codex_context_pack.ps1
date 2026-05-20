param(
  [string]$OutputPath = "",
  [switch]$Check,
  [switch]$Print
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

if (-not $OutputPath) {
  $OutputPath = Join-Path $RepoRoot "docs\codex_context_pack.md"
}

$forbiddenPathPatterns = @(
  'personal_os[\\/]',
  'evals[\\/]results',
  'tmp[\\/]agent_traces',
  'hermes_workspace[\\/]',
  'lexa_memory\.db',
  '\.env',
  'audit\.log',
  'bridge-audit\.log'
)

function Test-ForbiddenPackContent {
  param([string]$Text)
  $forbiddenText = @(
    '06_Inbox/Drafts/2026-',
    '05_Memory/Rollups/',
    'sk-',
    'service_role',
    'STRIPE_SECRET_KEY',
    'SUPABASE_SERVICE_ROLE'
  )
  foreach ($token in $forbiddenText) {
    if ($Text -like "*$token*") {
      throw "Generated context pack contains forbidden token: $token"
    }
  }
}

$hasGit = Test-Path -LiteralPath (Join-Path $RepoRoot ".git")
$head = if ($hasGit) { (git rev-parse --short HEAD 2>$null) } else { "source-copy-no-git" }
$recent = if ($hasGit) { @(git log --oneline -5 2>$null) } else { @() }
$remote = if ($hasGit) { @(git remote -v 2>$null) } else { @() }
$remoteStatus = if ($remote.Count -gt 0) { "configured" } else { "not configured" }

$recentLines = if ($recent.Count -gt 0) {
  ($recent | ForEach-Object { "- " + $_ }) -join [Environment]::NewLine
} else {
  "- unavailable"
}

$pack = @"
# Codex Context Pack

This file is generated from safe Lexa repository metadata and fixed release-readiness facts. It intentionally excludes Personal OS contents, user data, eval results, traces, logs, secrets, signing keys, certificates, and build artifacts.

## Current Project State

- Current Lexa commit: $head
- GitHub remote status: $remoteStatus
- Release targets: InternalRC, PublicRC, PublicRelease
- InternalRC may proceed with documented warnings.
- PublicRC/PublicRelease remain blocked until remote CI proof, VM installer proof, signing, website release target proof, and OS cleanup review are complete.

## Recent Commits

$recentLines

## Safe Context Sources

- AGENTS.md
- README.md
- docs/dev-testing.md
- docs/release/release_candidate_checklist.md
- docs/release/ci.md
- docs/release/signing_plan.md
- docs/release/website_strategy.md
- docs/release/os_repo_cleanup_plan.md
- evals/README.md

## Do Not Load Or Commit

- personal_os/ contents unless explicitly scoped by the user
- real memory databases, audit logs, bridge audit logs, traces, eval results, installers, build output, secrets, signing keys, certificates, private OS/Obsidian content

## Required Gates

- scripts\run_quality_gates.ps1 -Mode Quick
- scripts\run_quality_gates.ps1 -Mode Full
- scripts\run_quality_gates.ps1 -Mode CI
- scripts\run_eval_regression_gate.ps1
- scripts\run_release_candidate_check.ps1 -Target InternalRC

## Open PublicRC Blockers

- Remote GitHub Actions run is not yet proven when no GitHub remote is configured.
- Installer install/uninstall in a disposable VM or sandbox is not yet proven.
- Installer is unsigned.
- Website is currently a static external target without package-based build/lint proof.
- External OS cleanup remains a separate reviewed project.

## Codex Working Rules

- Do not use git add ..
- Do not delete files without explicit approval.
- Do not commit user data, generated artifacts, secrets, signing keys, certificates, or private OS/Obsidian content.
- Keep OS, Hermes, Website, Plugin, Electron, and release changes scoped to the active phase.
"@

Test-ForbiddenPackContent $pack

if ($Check) {
  foreach ($pattern in $forbiddenPathPatterns) {
    if ($OutputPath -match $pattern) {
      throw "OutputPath is forbidden for context-pack generation: $OutputPath"
    }
  }
}

if ($Print) {
  Write-Output $pack
  exit 0
}

$target = if ([System.IO.Path]::IsPathRooted($OutputPath)) { $OutputPath } else { Join-Path $RepoRoot $OutputPath }
$targetDir = Split-Path -Parent $target
if ($targetDir -and !(Test-Path -LiteralPath $targetDir)) {
  New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
}
Set-Content -LiteralPath $target -Value $pack -Encoding UTF8
Write-Host "Codex context pack written: $target"
exit 0

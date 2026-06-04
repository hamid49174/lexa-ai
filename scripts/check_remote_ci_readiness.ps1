param(
  [string]$Root = "",
  [string]$WorkflowPath = "",
  [switch]$Json
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
  $Root = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
} else {
  $Root = Resolve-Path -LiteralPath $Root
}

if (-not $WorkflowPath) {
  $WorkflowPath = Join-Path $Root ".github\workflows\quality-gates.yml"
} elseif (-not [System.IO.Path]::IsPathRooted($WorkflowPath)) {
  $WorkflowPath = Join-Path $Root $WorkflowPath
}

$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$nextSteps = New-Object System.Collections.Generic.List[string]

function Add-Failure {
  param([string]$Message)
  $failures.Add($Message) | Out-Null
}

function Add-Warning {
  param([string]$Message)
  $warnings.Add($Message) | Out-Null
}

function Add-NextStep {
  param([string]$Message)
  $nextSteps.Add($Message) | Out-Null
}

function Get-GitRemotes {
  if (!(Test-Path -LiteralPath (Join-Path $Root ".git"))) {
    return @()
  }
  Push-Location $Root
  try {
    return @(git remote -v 2>$null)
  } finally {
    Pop-Location
  }
}

function Test-GithubRemote {
  param([string[]]$Remotes)
  foreach ($remote in $Remotes) {
    if ($remote -match 'github\.com[:/]' -or $remote -match 'https://github\.com/') {
      return $true
    }
  }
  return $false
}

function Test-FileContains {
  param([string]$PathValue, [string]$Needle)
  if (!(Test-Path -LiteralPath $PathValue)) { return $false }
  return ((Get-Content -LiteralPath $PathValue -Raw) -like "*$Needle*")
}

$remotes = @(Get-GitRemotes)
$hasGithubRemote = Test-GithubRemote $remotes

if (-not $hasGithubRemote) {
  Add-Warning "Remote CI not yet proven because no GitHub remote is configured."
  Add-NextStep "Create or select the GitHub repository."
  Add-NextStep "Set the remote, push the branch, run GitHub Actions, and record the run URL plus commit SHA."
}

if (!(Test-Path -LiteralPath $WorkflowPath -PathType Leaf)) {
  Add-Failure "Workflow file is missing: $WorkflowPath"
} else {
  $workflowText = Get-Content -LiteralPath $WorkflowPath -Raw
  $unsafePatterns = @(
    @{ Name = "secret reference"; Pattern = '(?i)secrets\.' },
    @{ Name = "artifact upload"; Pattern = '(?i)(actions/upload-artifact|upload-artifact)' },
    @{ Name = "release action"; Pattern = '(?i)(action-gh-release|gh\s+release)' },
    @{ Name = "package publishing"; Pattern = '(?i)(npm\s+publish|electron-builder[^\r\n]*--publish)' },
    @{ Name = "cloud deployment"; Pattern = '(?i)(firebase\s+deploy|vercel\s+--prod|netlify\s+deploy|az\s+webapp\s+deploy)' },
    @{ Name = "user data path"; Pattern = '(?i)(personal_os|lexa_memory\.db|hermes_workspace|evals/results|tmp/agent_traces|bridge-audit\.log|audit\.log)' },
    @{ Name = "env file path"; Pattern = '(?i)(^|[\\/\s])\.env([\\/\s:]|$)' },
    @{ Name = "package-manager credential path"; Pattern = '(?i)(^|[\\/\s])\.(netrc|npmrc|pnpmrc|pypirc|yarnrc(\.yml)?)([\\/\s:]|$)|(^|[\\/\s])pip\.(conf|ini)([\\/\s:]|$)' },
    @{ Name = "cloud credential path"; Pattern = '(?i)(\.aws[\\/](credentials|config)|\.azure[\\/](accessTokens|azureProfile)\.json|\.config[\\/]gcloud[\\/]application_default_credentials\.json|\.docker[\\/]config\.json|\.gcloud[\\/]application_default_credentials\.json|\.kube[\\/]config)' },
    @{ Name = "machine credential file"; Pattern = '(?i)(^|[\\/\s])(credentials|secrets)\.(json|ya?ml|toml|ini|conf)([\\/\s:]|$)|(^|[\\/\s])client_secret[^\\/\s]*\.json([\\/\s:]|$)|(^|[\\/\s])service[-_]?account[^\\/\s]*\.json([\\/\s:]|$)' },
    @{ Name = "signing material path"; Pattern = '(?i)\.(pfx|p12|pem|ppk|key|pvk|cer|crt|spc|jks|keystore)([\\/\s:]|$)' }
  )
  foreach ($entry in $unsafePatterns) {
    if ($workflowText -match $entry.Pattern) {
      Add-Failure "Workflow safety failure: $($entry.Name)."
    }
  }
  if ($workflowText -notmatch 'windows-latest') {
    Add-Warning "Workflow does not explicitly use windows-latest."
  }
}

$qualityScript = Join-Path $Root "scripts\run_quality_gates.ps1"
$rcScript = Join-Path $Root "scripts\run_release_candidate_check.ps1"
if (!(Test-FileContains $qualityScript 'ValidateSet("Quick", "Full", "Eval", "CI")')) {
  Add-Failure "scripts\run_quality_gates.ps1 does not expose -Mode CI."
}
if (!(Test-FileContains $rcScript 'ValidateSet("InternalRC", "PublicRC", "PublicRelease")')) {
  Add-Failure "scripts\run_release_candidate_check.ps1 does not expose release targets."
}

$ready = ($failures.Count -eq 0 -and $hasGithubRemote)
$status = [pscustomobject]@{
  RemoteCIReady = if ($ready) { "yes" } else { "no" }
  HasGithubRemote = $hasGithubRemote
  WorkflowPath = $WorkflowPath
  Failures = @($failures)
  Warnings = @($warnings)
  NextSteps = @($nextSteps)
}

if ($Json) {
  $status | ConvertTo-Json -Depth 4
} else {
  Write-Host "Remote CI readiness"
  Write-Host "Root: $Root"
  Write-Host "Workflow: $WorkflowPath"
  Write-Host "RemoteCIReady: $($status.RemoteCIReady)"
  if ($failures.Count -gt 0) {
    Write-Host "Failures:"
    $failures | ForEach-Object { Write-Host "- $_" }
  }
  if ($warnings.Count -gt 0) {
    Write-Host "Warnings:"
    $warnings | ForEach-Object { Write-Host "- $_" }
  }
  if ($nextSteps.Count -gt 0) {
    Write-Host "Next steps:"
    $nextSteps | ForEach-Object { Write-Host "- $_" }
  }
}

if ($failures.Count -gt 0) {
  exit 1
}
exit 0

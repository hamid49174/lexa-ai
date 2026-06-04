param(
  [string]$ApiUrl = $env:LEXA_LICENSE_SMOKE_API_URL,
  [string]$LicenseKey = $env:LEXA_LICENSE_SMOKE_KEY,
  [string]$ExpectedPlan = $env:LEXA_LICENSE_SMOKE_EXPECTED_PLAN,
  [string]$InstanceToken = $env:LEXA_INSTANCE_TOKEN,
  [int]$TimeoutSec = 10,
  [switch]$AllowMissing
)

$ErrorActionPreference = "Stop"
$licensePattern = '^LEXA-[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}$'
$paidPlans = @("pro", "ultra")
$activeStatuses = @("active", "trialing")

function Format-MaskedLicenseKey {
  param([string]$Key)
  if ([string]::IsNullOrWhiteSpace($Key)) { return "<unset>" }
  $clean = $Key.Trim().ToUpperInvariant()
  if ($clean.Length -lt 16) { return "<redacted>" }
  return "$($clean.Substring(0, 10))...$($clean.Substring($clean.Length - 5))"
}

if ([string]::IsNullOrWhiteSpace($ApiUrl)) {
  $ApiUrl = "http://127.0.0.1:8000"
}
$ApiUrl = $ApiUrl.Trim().TrimEnd([char[]]@('/'))

Write-Host "Lexa paid license smoke"
Write-Host "ApiUrl: $ApiUrl"

if ($ApiUrl -notmatch '^https?://') {
  throw "LEXA_LICENSE_SMOKE_API_URL must start with http:// or https://."
}

if ([string]::IsNullOrWhiteSpace($LicenseKey)) {
  $message = "LEXA_LICENSE_SMOKE_KEY is not set. Paid license smoke needs a real paid license key from the target environment."
  if ($AllowMissing) {
    Write-Warning $message
    exit 0
  }
  throw $message
}

$LicenseKey = $LicenseKey.Trim().ToUpperInvariant()
Write-Host "LicenseKey: $(Format-MaskedLicenseKey $LicenseKey)"

if ($LicenseKey -notmatch $licensePattern) {
  throw "LEXA_LICENSE_SMOKE_KEY has an invalid format. Expected LEXA-XXXXX-XXXXX-XXXXX-XXXXX with uppercase A-F/0-9 groups."
}

$headers = @{}
if (-not [string]::IsNullOrWhiteSpace($InstanceToken)) {
  $headers["X-Lexa-Local-Token"] = $InstanceToken
}

$uri = "$ApiUrl/license/validate"
$body = @{ license_key = $LicenseKey } | ConvertTo-Json -Compress

try {
  $response = Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -ContentType "application/json" -Body $body -TimeoutSec $TimeoutSec
} catch {
  throw "Paid license smoke request failed: $($_.Exception.Message)"
}

if ($null -eq $response) {
  throw "Paid license smoke returned no JSON response."
}

$valid = $response.valid -eq $true
$plan = ([string]$response.plan).Trim().ToLowerInvariant()
$status = ([string]$response.status).Trim().ToLowerInvariant()
$expires = ([string]$response.expires).Trim()

if (-not $valid) {
  throw "Paid license smoke failed: backend returned valid=false, plan='$plan', status='$status'."
}

if ($paidPlans -notcontains $plan) {
  throw "Paid license smoke failed: expected a paid plan ($($paidPlans -join ', ')), got '$plan'."
}

if ($activeStatuses -notcontains $status) {
  throw "Paid license smoke failed: expected an active status ($($activeStatuses -join ', ')), got '$status'."
}

if (-not [string]::IsNullOrWhiteSpace($ExpectedPlan)) {
  $expected = $ExpectedPlan.Trim().ToLowerInvariant()
  if ($paidPlans -notcontains $expected) {
    throw "LEXA_LICENSE_SMOKE_EXPECTED_PLAN must be one of: $($paidPlans -join ', ')."
  }
  if ($plan -ne $expected) {
    throw "Paid license smoke failed: expected plan '$expected', got '$plan'."
  }
}

if ([string]::IsNullOrWhiteSpace($expires)) {
  Write-Warning "Paid license response has no expires value. This may be valid for a lifetime entitlement, but should be reviewed before PublicRC."
}

Write-Host "ok: backend accepted paid license ($plan / $status)"
exit 0

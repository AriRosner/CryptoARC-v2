param(
  [switch]$Json,
  [switch]$Strict
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runtime.ps1")

$root = Get-CryptoArcRoot
$frontendRoot = Join-Path $root "frontend"
$packageManager = Resolve-CryptoArcPackageManager

if ($packageManager.Name -ne "npm") {
  throw "Frontend audit currently requires npm because the project is locked with package-lock.json."
}

Push-Location $frontendRoot
try {
  $auditText = (& $packageManager.FilePath audit --json 2>&1) -join "`n"
  $auditExitCode = $LASTEXITCODE
} finally {
  Pop-Location
}

try {
  $audit = $auditText | ConvertFrom-Json
} catch {
  throw "npm audit did not return parseable JSON. Raw output: $auditText"
}

$acknowledgedChain = @("@solana/web3.js", "jayson", "uuid")
$vulnerabilities = @()
if ($audit.vulnerabilities) {
  foreach ($property in $audit.vulnerabilities.PSObject.Properties) {
    $item = $property.Value
    $fix = $item.fixAvailable
    $fixName = if ($fix -is [bool]) { "" } else { [string]$fix.name }
    $fixVersion = if ($fix -is [bool]) { "" } else { [string]$fix.version }
    $isSemVerMajor = if ($fix -is [bool]) { $false } else { [bool]$fix.isSemVerMajor }
    $acknowledged = $acknowledgedChain -contains $item.name -and $item.severity -eq "moderate" -and $fixName -eq "@solana/web3.js" -and $fixVersion -eq "0.0.3" -and $isSemVerMajor
    $vulnerabilities += [ordered]@{
      name                  = [string]$item.name
      severity              = [string]$item.severity
      is_direct             = [bool]$item.isDirect
      via                   = @($item.via | ForEach-Object { if ($_ -is [string]) { $_ } else { [string]$_.name } })
      fix_available         = if ($fix -is [bool]) { $fix } else { [ordered]@{ name = $fixName; version = $fixVersion; is_semver_major = $isSemVerMajor } }
      acknowledged_exception = $acknowledged
    }
  }
}

$severityRank = @{ info = 0; low = 1; moderate = 2; high = 3; critical = 4 }
$blockers = @()
$warnings = @()
foreach ($item in $vulnerabilities) {
  $rank = $severityRank[$item.severity]
  if ($null -eq $rank) {
    $rank = 2
  }
  if ($rank -ge 3) {
    $blockers += "$($item.name) has $($item.severity) severity and must be resolved before release."
  } elseif (-not $item.acknowledged_exception -and $rank -ge 2) {
    $blockers += "$($item.name) is an unacknowledged moderate advisory."
  } elseif ($item.acknowledged_exception) {
    $warnings += "$($item.name) remains in the acknowledged @solana/web3.js -> jayson -> uuid advisory chain; npm's available fix downgrades @solana/web3.js to 0.0.3."
  }
}

$metadata = $audit.metadata
$counts = if ($metadata -and $metadata.vulnerabilities) { $metadata.vulnerabilities } else { [ordered]@{} }
$status = if ($blockers.Count -gt 0) { "blocked" } elseif ($warnings.Count -gt 0 -or $auditExitCode -ne 0) { "review" } else { "ready" }
$operatorAction = if ($status -eq "ready") {
  "Frontend dependency audit is clear."
} elseif ($status -eq "review") {
  "Review acknowledged moderate advisories and do not apply npm's breaking Solana downgrade without a compatibility plan."
} else {
  "Resolve high, critical, or unacknowledged advisories before release or live work."
}

$report = [ordered]@{
  artifact_type          = "cryptoarc_frontend_dependency_audit"
  format_version         = 1
  generated_at           = (Get-Date).ToUniversalTime().ToString("o")
  status                 = $status
  npm_exit_code          = $auditExitCode
  counts                 = $counts
  vulnerabilities        = $vulnerabilities
  blockers               = @($blockers | Select-Object -Unique)
  warnings               = @($warnings | Select-Object -Unique)
  acknowledged_exception = "moderate @solana/web3.js -> jayson -> uuid advisory; npm fix suggests @solana/web3.js@0.0.3, which is a breaking downgrade"
  operator_action        = $operatorAction
}

if ($Json) {
  $report | ConvertTo-Json -Depth 8
} else {
  Write-Host "CryptoARC frontend dependency audit: $status"
  Write-Host "Vulnerabilities: total=$($counts.total) moderate=$($counts.moderate) high=$($counts.high) critical=$($counts.critical)"
  foreach ($warning in $warnings) {
    Write-Host "[WARN] $warning"
  }
  foreach ($blocker in $blockers) {
    Write-Host "[FAIL] $blocker"
  }
  Write-Host $operatorAction
}

if ($Strict -and $blockers.Count -gt 0) {
  exit 1
}

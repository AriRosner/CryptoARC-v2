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

$schemaErrors = @()
if ($null -eq $audit) {
  $schemaErrors += "report is null"
} else {
  $reportVersionProperty = $audit.PSObject.Properties["auditReportVersion"]
  if ($null -eq $reportVersionProperty -or [string]$reportVersionProperty.Value -ne "2") {
    $schemaErrors += "auditReportVersion must be 2"
  }
  $vulnerabilitiesProperty = $audit.PSObject.Properties["vulnerabilities"]
  if ($null -eq $vulnerabilitiesProperty -or $vulnerabilitiesProperty.Value -isnot [pscustomobject]) {
    $schemaErrors += "vulnerabilities must be an object"
  }
  $metadataProperty = $audit.PSObject.Properties["metadata"]
  $countsProperty = if ($null -ne $metadataProperty -and $metadataProperty.Value -is [pscustomobject]) {
    $metadataProperty.Value.PSObject.Properties["vulnerabilities"]
  } else {
    $null
  }
  if ($null -eq $countsProperty -or $countsProperty.Value -isnot [pscustomobject]) {
    $schemaErrors += "metadata.vulnerabilities must be an object"
  } else {
    foreach ($countName in @("info", "low", "moderate", "high", "critical", "total")) {
      $countProperty = $countsProperty.Value.PSObject.Properties[$countName]
      [long]$parsedCount = 0
      if ($null -eq $countProperty -or -not [long]::TryParse([string]$countProperty.Value, [ref]$parsedCount) -or $parsedCount -lt 0) {
        $schemaErrors += "metadata.vulnerabilities.$countName must be a non-negative integer"
      }
    }
  }
}
$schemaToolingError = if ($schemaErrors.Count -gt 0) {
  "invalid npm audit JSON schema: $($schemaErrors -join '; ')"
} else {
  $null
}

$acknowledgedChain = @("@solana/web3.js", "jayson", "uuid")
$vulnerabilities = @()
if (-not $schemaToolingError -and $audit.vulnerabilities) {
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
if (-not $schemaToolingError) {
  $observedCounts = [ordered]@{ info = 0; low = 0; moderate = 0; high = 0; critical = 0; total = $vulnerabilities.Count }
  foreach ($item in $vulnerabilities) {
    $severity = ([string]$item.severity).ToLowerInvariant()
    if ($observedCounts.Contains($severity) -and $severity -ne "total") {
      $observedCounts[$severity] += 1
    } else {
      $schemaErrors += "vulnerability $($item.name) has unsupported severity '$severity'"
    }
  }
  foreach ($countName in @("info", "low", "moderate", "high", "critical", "total")) {
    $reportedCount = [long]$audit.metadata.vulnerabilities.PSObject.Properties[$countName].Value
    if ($reportedCount -ne $observedCounts[$countName]) {
      $schemaErrors += "metadata.vulnerabilities.$countName=$reportedCount does not match parsed entries=$($observedCounts[$countName])"
    }
  }
  if ($schemaErrors.Count -gt 0) {
    $schemaToolingError = "invalid npm audit JSON schema: $($schemaErrors -join '; ')"
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
$toolingError = $schemaToolingError
if ($auditExitCode -gt 1) {
  $toolingError = "npm audit exited with code $auditExitCode; treat this as a tooling or registry failure and rerun the audit."
} elseif ($auditExitCode -eq 1 -and $vulnerabilities.Count -eq 0) {
  $toolingError = "npm audit exited with code 1 without parsed vulnerability entries; treat this as a tooling or registry failure and rerun the audit."
}
if ($toolingError) {
  $blockers += $toolingError
}

$metadata = $audit.metadata
$counts = if (-not $schemaToolingError) { $metadata.vulnerabilities } else { [ordered]@{} }
$status = if ($blockers.Count -gt 0) { "blocked" } elseif ($warnings.Count -gt 0 -or $auditExitCode -ne 0) { "review" } else { "ready" }
$operatorAction = if ($status -eq "ready") {
  "Frontend dependency audit is clear."
} elseif ($status -eq "review") {
  "Review acknowledged moderate advisories and do not apply npm's breaking Solana downgrade without a compatibility plan."
} else {
  "Resolve high, critical, or unacknowledged advisories before release or live work."
}
$acknowledgedException = if ($warnings.Count -gt 0) {
  "moderate @solana/web3.js -> jayson -> uuid advisory; npm fix suggests @solana/web3.js@0.0.3, which is a breaking downgrade"
} else {
  $null
}

$report = [ordered]@{
  artifact_type          = "cryptoarc_frontend_dependency_audit"
  format_version         = 1
  generated_at           = (Get-Date).ToUniversalTime().ToString("o")
  status                 = $status
  npm_exit_code          = $auditExitCode
  tooling_error          = $toolingError
  counts                 = $counts
  vulnerabilities        = $vulnerabilities
  blockers               = @($blockers | Select-Object -Unique)
  warnings               = @($warnings | Select-Object -Unique)
  acknowledged_exception = $acknowledgedException
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

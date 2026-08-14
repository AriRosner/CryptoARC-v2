param(
  [switch]$Json,
  [switch]$Strict,
  [string]$AuditJsonPath = "",
  [string]$AsOfUtc = ""
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runtime.ps1")

$root = Get-CryptoArcRoot
$mobileRoot = Join-Path $root "mobile"
$policyPath = Join-Path $PSScriptRoot "mobile-audit-exception.json"
$blockers = @()
$warnings = @()
$auditExitCode = 0
$audit = $null
$policy = $null
$policyExpiresAt = ""
$exceptionActive = $false

try {
  if (($AuditJsonPath -or $AsOfUtc) -and $env:CRYPTOARC_AUDIT_FIXTURE_TEST -ne "true") {
    throw "Audit JSON and clock injection are test-only and require CRYPTOARC_AUDIT_FIXTURE_TEST=true."
  }
  $policyText = Get-Content -LiteralPath $policyPath -Raw
  $policy = $policyText | ConvertFrom-Json
  if ([int]$policy.format_version -ne 1) {
    throw "unsupported exception policy format"
  }
  $expiresMatch = [regex]::Match($policyText, '"expires_at"\s*:\s*"(?<value>[^"]+)"')
  if (-not $expiresMatch.Success) {
    throw "exception policy expires_at must be an ISO-8601 string"
  }
  $policyExpiresAt = $expiresMatch.Groups["value"].Value
  $packageManager = Resolve-CryptoArcPackageManager
  if ($packageManager.Name -ne "npm") {
    throw "Mobile audit requires npm because mobile/package-lock.json is authoritative."
  }

  if ($AuditJsonPath) {
    $auditText = Get-Content -LiteralPath $AuditJsonPath -Raw
    $audit = $auditText | ConvertFrom-Json
    $auditExitCode = if (@($audit.vulnerabilities.PSObject.Properties).Count -gt 0) { 1 } else { 0 }
  } else {
    Push-Location $mobileRoot
    try {
      $auditText = (& $packageManager.FilePath audit --omit=dev --audit-level=high --json 2>&1) -join "`n"
      $auditExitCode = $LASTEXITCODE
    } finally {
      Pop-Location
    }
    $audit = $auditText | ConvertFrom-Json
  }

  if ([string]$audit.auditReportVersion -ne "2") {
    throw "npm audit JSON must use auditReportVersion 2"
  }
  if ($audit.vulnerabilities -isnot [pscustomobject]) {
    throw "npm audit JSON vulnerabilities must be an object"
  }

  $vulnerabilityProperties = @($audit.vulnerabilities.PSObject.Properties)
  if ($vulnerabilityProperties.Count -eq 0) {
    if ($auditExitCode -ne 0) {
      throw "npm audit exited nonzero without vulnerability entries"
    }
  } else {
    $asOf = if ($AsOfUtc) { [DateTimeOffset]::Parse($AsOfUtc) } else { [DateTimeOffset]::UtcNow }
    $expires = [DateTimeOffset]::Parse(
      $policyExpiresAt,
      [Globalization.CultureInfo]::InvariantCulture,
      [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
    )
    if ($asOf -gt $expires) {
      $blockers += "The mobile image-size audit exception expired at $policyExpiresAt."
    }

    $observedNames = @($vulnerabilityProperties | ForEach-Object { [string]$_.Name } | Sort-Object)
    $allowedNames = @($policy.cascade_packages | ForEach-Object { [string]$_ } | Sort-Object)
    if (@(Compare-Object -ReferenceObject $allowedNames -DifferenceObject $observedNames).Count -ne 0) {
      $blockers += "The npm audit vulnerability set differs from the approved image-size cascade."
    }
    foreach ($property in $vulnerabilityProperties) {
      if ([string]$property.Value.severity -ne "high") {
        $blockers += "$($property.Name) has an unapproved severity."
      }
    }

    $imageProperty = $audit.vulnerabilities.PSObject.Properties["image-size"]
    if ($null -eq $imageProperty) {
      $blockers += "The approved image-size root advisory is absent from the reported cascade."
    } else {
      $observedAdvisories = @(
        $imageProperty.Value.via |
          Where-Object { $_ -isnot [string] } |
          ForEach-Object { ([string]$_.url).Split("/")[-1] } |
          Sort-Object
      )
      $allowedAdvisories = @($policy.advisories | ForEach-Object { [string]$_ } | Sort-Object)
      if (@(Compare-Object -ReferenceObject $allowedAdvisories -DifferenceObject $observedAdvisories).Count -ne 0) {
        $blockers += "The image-size advisory IDs differ from the approved exception."
      }
    }

    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCommand) {
      throw "Node.js is required to inspect mobile/package-lock.json."
    }
    $lockPath = Join-Path $mobileRoot "package-lock.json"
    $lockedVersion = (& $nodeCommand.Source -e "const l=require(process.argv[1]); process.stdout.write(l.packages?.['node_modules/image-size']?.version ?? '')" $lockPath) -join ""
    if ($LASTEXITCODE -ne 0 -or $lockedVersion -ne [string]$policy.installed_version) {
      $blockers += "The locked image-size version differs from the approved $($policy.installed_version)."
    }

    $sourceFiles = @()
    foreach ($sourceRootName in @("app", "src")) {
      $sourceRoot = Join-Path $mobileRoot $sourceRootName
      if (Test-Path -LiteralPath $sourceRoot) {
        $sourceFiles += Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Include *.js,*.jsx,*.ts,*.tsx
      }
    }
    $forbiddenImport = $sourceFiles | Select-String -Pattern '(?i)(from\s+["''](?:image-size|metro)["'']|require\(["''](?:image-size|metro)["'']\))'
    if ($forbiddenImport) {
      $blockers += "Mobile application source imports Metro or image-size; the build-only boundary no longer holds."
    }

    $assetsRoot = Join-Path $mobileRoot "assets"
    $pngSignature = [byte[]](0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
    foreach ($asset in Get-ChildItem -LiteralPath $assetsRoot -Recurse -File) {
      $extension = $asset.Extension.ToLowerInvariant()
      if ($extension -eq ".ttf") {
        continue
      }
      if ($extension -ne ".png") {
        $blockers += "Unapproved mobile asset type: $($asset.FullName)."
        continue
      }
      $stream = [System.IO.File]::OpenRead($asset.FullName)
      try {
        $header = New-Object byte[] 8
        $read = $stream.Read($header, 0, 8)
      } finally {
        $stream.Dispose()
      }
      if ($read -ne 8 -or @(Compare-Object -ReferenceObject $pngSignature -DifferenceObject $header -SyncWindow 0).Count -ne 0) {
        $blockers += "Mobile PNG asset has an invalid signature: $($asset.FullName)."
      }
    }

    if ($blockers.Count -eq 0) {
      $exceptionActive = $true
      $warnings += "Time-bounded image-size build-tool exception is active through $policyExpiresAt; tracking issue: $($policy.tracking_issue)."
    }
  }
} catch {
  $blockers += "Mobile dependency audit tooling failed closed: $($_.Exception.Message) [$($_.InvocationInfo.ScriptLineNumber)]"
}

if ($auditExitCode -gt 1) {
  $blockers += "npm audit exited with code $auditExitCode."
}
$status = if ($blockers.Count -gt 0) { "blocked" } elseif ($exceptionActive) { "review" } else { "ready" }
$report = [ordered]@{
  artifact_type = "cryptoarc_mobile_dependency_audit"
  format_version = 1
  generated_at = [DateTimeOffset]::UtcNow.ToString("o")
  status = $status
  npm_exit_code = $auditExitCode
  exception = [ordered]@{
    active = $exceptionActive
    package = if ($policy) { [string]$policy.package } else { $null }
    expires_at = if ($policy) { $policyExpiresAt } else { $null }
    advisories = if ($policy) { @($policy.advisories) } else { @() }
  }
  blockers = @($blockers | Select-Object -Unique)
  warnings = @($warnings | Select-Object -Unique)
}

if ($Json) {
  $report | ConvertTo-Json -Depth 8
} else {
  Write-Host "CryptoARC mobile dependency audit: $status"
  foreach ($warning in $report.warnings) { Write-Host "[WARN] $warning" }
  foreach ($blocker in $report.blockers) { Write-Host "[FAIL] $blocker" }
}

if ($Strict -and $status -eq "blocked") {
  exit 1
}

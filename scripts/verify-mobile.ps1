param(
  [switch]$SkipDiagnostics,
  [switch]$SkipAndroidBuildSanity
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runtime.ps1")

$root = Get-CryptoArcRoot
$mobileRoot = Join-Path $root "mobile"

if (-not (Test-Path -LiteralPath $mobileRoot)) {
  throw "mobile app directory is missing."
}

$packageManager = Resolve-CryptoArcPackageManager
$nodeModules = Join-Path $mobileRoot "node_modules"

Push-Location $mobileRoot
try {
  if (-not (Test-Path -LiteralPath $nodeModules)) {
    Write-Host "Installing mobile dependencies"
    if ($packageManager.Name -eq "npm") {
      Invoke-CryptoArcNative -FilePath $packageManager.FilePath -Arguments @("install", "--legacy-peer-deps")
    } else {
      Invoke-CryptoArcNative -FilePath $packageManager.FilePath -Arguments @("install", "--no-frozen-lockfile")
    }
  }

  Write-Host "Running mobile TypeScript checks"
  Invoke-CryptoArcNative -FilePath $packageManager.FilePath -Arguments @("run", "typecheck")

  Write-Host "Running mobile unit/component tests"
  Invoke-CryptoArcNative -FilePath $packageManager.FilePath -Arguments @("test")

  Write-Host "Running mobile production dependency audit"
  Invoke-CryptoArcNative -FilePath $packageManager.FilePath -Arguments @("audit", "--omit=dev", "--audit-level=high")

  if (-not $SkipDiagnostics) {
    Write-Host "Running Expo diagnostics"
    Invoke-CryptoArcNative -FilePath $packageManager.FilePath -Arguments @("run", "diagnostics")
  }

  if (-not $SkipAndroidBuildSanity) {
    Write-Host "Running Android export sanity check"
    Invoke-CryptoArcNative -FilePath $packageManager.FilePath -Arguments @("run", "export:android")
  }
} finally {
  Pop-Location
}

Write-Host "Mobile verification checks passed."

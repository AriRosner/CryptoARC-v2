param(
  [switch]$SkipFrontendBuild,
  [switch]$SkipBackendTests,
  [switch]$SkipMobileBuild
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runtime.ps1")

$root = Get-CryptoArcRoot
$frontendRoot = Join-Path $root "frontend"
$python = Resolve-CryptoArcPython

Set-Location $root

Write-Host "Running setup diagnostics"
& (Join-Path $PSScriptRoot "doctor.ps1") -Strict
$doctorExitCode = $LASTEXITCODE
if ($doctorExitCode -ne 0) {
  throw "Setup diagnostics failed with exit code ${doctorExitCode}."
}

Write-Host "Running backend import smoke test"
$env:PYTHONPATH = "backend"
Invoke-CryptoArcNative -FilePath $python -Arguments @("-c", "from app.core.state import BotState; from solders.keypair import Keypair; print('backend imports ok')")

if (-not $SkipBackendTests) {
  Write-Host "Running backend unit tests"
  Invoke-CryptoArcNative -FilePath $python -Arguments @("-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-q")
}

Write-Host "Checking backend and frontend settings contract"
Invoke-CryptoArcNative -FilePath $python -Arguments @("scripts/check_settings_contract.py")

if (-not $SkipFrontendBuild) {
  Assert-CryptoArcFrontendDependencies
  $packageManager = Resolve-CryptoArcPackageManager
  Push-Location $frontendRoot
  try {
    Write-Host "Checking frontend polling stability"
    Invoke-CryptoArcNative -FilePath $packageManager.FilePath -Arguments @("run", "check:polling")
    Write-Host "Checking frontend execution-readiness contract"
    Invoke-CryptoArcNative -FilePath $packageManager.FilePath -Arguments @("run", "check:execution-readiness")
    Write-Host "Running frontend build"
    Invoke-CryptoArcNative -FilePath $packageManager.FilePath -Arguments @("run", "build")
  } finally {
    Pop-Location
  }
}

if (-not $SkipMobileBuild) {
  Write-Host "Running mobile verification"
  & (Join-Path $PSScriptRoot "verify-mobile.ps1")
}

Write-Host "Checking local Markdown links"
& (Join-Path $PSScriptRoot "check-doc-links.ps1")

Write-Host "All verification checks passed."

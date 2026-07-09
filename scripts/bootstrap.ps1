param(
  [switch]$SkipFrontend,
  [switch]$SkipBackend,
  [switch]$ForceFrontendInstall
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runtime.ps1")

$root = Get-CryptoArcRoot
$frontendRoot = Join-Path $root "frontend"
$venvRoot = Join-Path $root ".venv"
$envPath = Join-Path $root ".env"
$envExamplePath = Join-Path $root ".env.example"

Set-Location $root

if (-not $SkipBackend) {
  if (-not (Test-Path -LiteralPath $venvRoot)) {
    $creator = Resolve-CryptoArcVenvCreator
    Write-Host "Creating Python virtual environment at .venv"
    Invoke-CryptoArcNative -FilePath $creator.FilePath -Arguments @($creator.Arguments + @($venvRoot))
  } else {
    Write-Host "Python virtual environment already exists at .venv"
  }

  $python = Resolve-CryptoArcPython
  Write-Host "Installing backend dependencies"
  Invoke-CryptoArcNative -FilePath $python -Arguments @("-m", "pip", "install", "--upgrade", "pip")
  Invoke-CryptoArcNative -FilePath $python -Arguments @("-m", "pip", "install", "-r", (Join-Path $root "backend\requirements.txt"))
}

if (-not $SkipFrontend) {
  $packageManager = Resolve-CryptoArcPackageManager
  $nodeModules = Join-Path $frontendRoot "node_modules"
  if ($ForceFrontendInstall -or -not (Test-Path -LiteralPath $nodeModules)) {
    Write-Host "Installing frontend dependencies"
    Push-Location $frontendRoot
    try {
      $installArgs = Get-CryptoArcFrontendInstallArguments -PackageManager $packageManager -CleanInstall:(Test-Path -LiteralPath (Join-Path $frontendRoot "package-lock.json"))
      Invoke-CryptoArcNative -FilePath $packageManager.FilePath -Arguments $installArgs
    } finally {
      Pop-Location
    }
  } else {
    Write-Host "Frontend dependencies already exist at frontend\node_modules"
  }
}

if (-not (Test-Path -LiteralPath $envPath) -and (Test-Path -LiteralPath $envExamplePath)) {
  Copy-Item -LiteralPath $envExamplePath -Destination $envPath
  Write-Host "Created .env from .env.example"
} elseif (Test-Path -LiteralPath $envPath) {
  Write-Host ".env already exists"
}

Write-Host "CryptoARC bootstrap complete."
Write-Host "Run scripts\verify.ps1 to validate the local environment."

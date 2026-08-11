param(
  [switch]$Json,
  [switch]$Strict
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runtime.ps1")

$root = Get-CryptoArcRoot
$frontendRoot = Join-Path $root "frontend"
$checks = New-Object System.Collections.Generic.List[object]

function Add-CryptoArcDoctorCheck {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Id,
    [Parameter(Mandatory = $true)]
    [string]$Label,
    [Parameter(Mandatory = $true)]
    [ValidateSet("pass", "warn", "fail")]
    [string]$Status,
    [Parameter(Mandatory = $true)]
    [string]$Value,
    [Parameter(Mandatory = $true)]
    [string]$Action
  )

  $script:checks.Add([ordered]@{
      id     = $Id
      label  = $Label
      status = $Status
      value  = $Value
      action = $Action
    }) | Out-Null
}

function Invoke-CryptoArcDoctorVersion {
  param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,
    [string[]]$Arguments = @("--version")
  )

  try {
    $output = & $FilePath @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
      return ""
    }
    return (($output | Select-Object -First 1) -join "").Trim()
  } catch {
    return ""
  }
}

function Test-CryptoArcPythonImport {
  param(
    [Parameter(Mandatory = $true)]
    [string]$PythonPath,
    [Parameter(Mandatory = $true)]
    [string]$ImportCode
  )

  try {
    $env:PYTHONPATH = Join-Path $root "backend"
    & $PythonPath -c $ImportCode 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
  } catch {
    return $false
  }
}

$backendEntry = Join-Path $root "backend\app\main.py"
$frontendPackage = Join-Path $frontendRoot "package.json"
if ((Test-Path -LiteralPath $backendEntry) -and (Test-Path -LiteralPath $frontendPackage)) {
  Add-CryptoArcDoctorCheck "repo_root" "Repository root" "pass" $root "Run commands from this checkout."
} else {
  Add-CryptoArcDoctorCheck "repo_root" "Repository root" "fail" $root "Run this script from the CryptoARC-v2 checkout."
}

$globalPython = $null
try {
  $creator = Resolve-CryptoArcVenvCreator
  $globalPython = $creator.FilePath
  $version = Invoke-CryptoArcDoctorVersion $globalPython @("--version")
  $value = if ($version) { $version } else { $globalPython }
  Add-CryptoArcDoctorCheck "python_available" "Python available" "pass" $value "Python can create or run the local virtual environment."
} catch {
  Add-CryptoArcDoctorCheck "python_available" "Python available" "fail" "missing" "Install Python, set CRYPTOARC_PYTHON, or restore Python to PATH."
}

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$configuredPython = Resolve-ExistingPath @(
  $venvPython,
  $env:CRYPTOARC_PYTHON
)
if ($configuredPython) {
  $version = Invoke-CryptoArcDoctorVersion $configuredPython @("--version")
  $value = if ($version) { "$version ($configuredPython)" } else { $configuredPython }
  Add-CryptoArcDoctorCheck "venv" "Configured Python environment" "pass" $value "Use this configured Python for backend commands."
} else {
  Add-CryptoArcDoctorCheck "venv" "Configured Python environment" "fail" "missing" "Run scripts\bootstrap.ps1 to create .venv or set CRYPTOARC_PYTHON."
}

if ($configuredPython) {
  $backendReady = Test-CryptoArcPythonImport $configuredPython "import fastapi; import solders; from solders.keypair import Keypair; from app.core.state import BotState"
  if ($backendReady) {
    Add-CryptoArcDoctorCheck "backend_imports" "Backend imports" "pass" "fastapi + solders + app" "Backend dependencies are importable."
  } else {
    Add-CryptoArcDoctorCheck "backend_imports" "Backend imports" "fail" "missing dependency" "Run scripts\bootstrap.ps1 or install backend\requirements.txt into .venv."
  }
} else {
  Add-CryptoArcDoctorCheck "backend_imports" "Backend imports" "fail" "no configured Python" "Create .venv or set CRYPTOARC_PYTHON before checking backend dependencies."
}

try {
  $packageManager = Resolve-CryptoArcPackageManager
  $version = Invoke-CryptoArcDoctorVersion $packageManager.FilePath @("--version")
  Add-CryptoArcDoctorCheck "node_package_manager" "Node package manager" "pass" "$($packageManager.Name) $version" "Frontend package manager is available."
} catch {
  Add-CryptoArcDoctorCheck "node_package_manager" "Node package manager" "fail" "missing" "Install Node.js/npm, set CRYPTOARC_NPM, or set CRYPTOARC_PNPM."
}

$nodeModules = Join-Path $frontendRoot "node_modules"
if (Test-Path -LiteralPath $nodeModules) {
  Add-CryptoArcDoctorCheck "frontend_dependencies" "Frontend dependencies" "pass" "frontend\node_modules" "Frontend dependencies are installed."
} else {
  Add-CryptoArcDoctorCheck "frontend_dependencies" "Frontend dependencies" "fail" "missing" "Run scripts\bootstrap.ps1 or install frontend dependencies."
}

$solanaPackage = Join-Path $frontendRoot "node_modules\@solana\web3.js\package.json"
if (Test-Path -LiteralPath $solanaPackage) {
  try {
    $solanaMetadata = Get-Content -LiteralPath $solanaPackage -Raw | ConvertFrom-Json
    Add-CryptoArcDoctorCheck "solana_web3" "Solana frontend package" "pass" "@solana/web3.js $($solanaMetadata.version)" "Solana frontend package is installed for wallet and transaction tooling."
  } catch {
    Add-CryptoArcDoctorCheck "solana_web3" "Solana frontend package" "warn" "installed, unreadable version" "Reinstall frontend dependencies if Solana package metadata is corrupted."
  }
} else {
  Add-CryptoArcDoctorCheck "solana_web3" "Solana frontend package" "fail" "missing" "Install frontend dependencies; @solana/web3.js is required by the live workspace."
}

$envPath = Join-Path $root ".env"
if (Test-Path -LiteralPath $envPath) {
  Add-CryptoArcDoctorCheck "env_file" ".env file" "pass" ".env" "Local environment file exists."
} else {
  Add-CryptoArcDoctorCheck "env_file" ".env file" "warn" "missing" "Run scripts\bootstrap.ps1 or copy .env.example to .env before operating the app."
}

$failures = @($checks | Where-Object { $_.status -eq "fail" })
$warnings = @($checks | Where-Object { $_.status -eq "warn" })
$checkArray = @($checks | ForEach-Object { $_ })
$blockerActions = @($failures | ForEach-Object { $_["action"] })
$warningActions = @($warnings | ForEach-Object { $_["action"] })
$status = if ($failures.Count -gt 0) { "blocked" } elseif ($warnings.Count -gt 0) { "review" } else { "ready" }
$operatorAction = if ($status -eq "ready") { "Environment diagnostics are clear; run scripts\verify.ps1 before release or live work." } elseif ($status -eq "review") { "Review warnings, then run scripts\verify.ps1 before release or live work." } else { "Resolve failed diagnostics before running the app, tests, or live workflows." }
$report = New-Object PSObject
$report | Add-Member -NotePropertyName "artifact_type" -NotePropertyValue "cryptoarc_setup_diagnostics"
$report | Add-Member -NotePropertyName "format_version" -NotePropertyValue 1
$report | Add-Member -NotePropertyName "generated_at" -NotePropertyValue (Get-Date).ToUniversalTime().ToString("o")
$report | Add-Member -NotePropertyName "status" -NotePropertyValue $status
$report | Add-Member -NotePropertyName "blockers" -NotePropertyValue $blockerActions
$report | Add-Member -NotePropertyName "warnings" -NotePropertyValue $warningActions
$report | Add-Member -NotePropertyName "checks" -NotePropertyValue $checkArray
$report | Add-Member -NotePropertyName "operator_action" -NotePropertyValue $operatorAction

if ($Json) {
  $report | ConvertTo-Json -Depth 6
} else {
  Write-Host "CryptoARC setup diagnostics: $status"
  foreach ($check in $checks) {
    $marker = if ($check.status -eq "pass") { "[OK]" } elseif ($check.status -eq "warn") { "[WARN]" } else { "[FAIL]" }
    Write-Host "$marker $($check.label): $($check.value)"
    if ($check.status -ne "pass") {
      Write-Host "      $($check.action)"
    }
  }
  Write-Host $report.operator_action
}

if ($Strict -and $failures.Count -gt 0) {
  exit 1
}

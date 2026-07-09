$ErrorActionPreference = "Stop"

function Get-CryptoArcRoot {
  return (Split-Path -Parent $PSScriptRoot)
}

function Resolve-ExistingPath {
  param(
    [string[]]$Candidates
  )

  foreach ($candidate in $Candidates) {
    if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate)) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  return $null
}

function Resolve-CryptoArcPython {
  param(
    [switch]$AllowGlobal
  )

  $root = Get-CryptoArcRoot
  $localPython = Resolve-ExistingPath @(
    (Join-Path $root ".venv\Scripts\python.exe"),
    $env:CRYPTOARC_PYTHON
  )
  if ($localPython) {
    return $localPython
  }

  if ($AllowGlobal) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
      return $pythonCommand.Source
    }
  }

  throw "Python runtime not found. Run scripts\bootstrap.ps1 first, install Python, or set CRYPTOARC_PYTHON to a python.exe path."
}

function Resolve-CryptoArcVenvCreator {
  $explicitPython = Resolve-ExistingPath @($env:CRYPTOARC_PYTHON)
  if ($explicitPython) {
    return @{ FilePath = $explicitPython; Arguments = @("-m", "venv") }
  }

  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCommand) {
    return @{ FilePath = $pythonCommand.Source; Arguments = @("-m", "venv") }
  }

  $pyCommand = Get-Command py -ErrorAction SilentlyContinue
  if ($pyCommand) {
    return @{ FilePath = $pyCommand.Source; Arguments = @("-3", "-m", "venv") }
  }

  throw "Cannot create .venv because Python was not found. Install Python or set CRYPTOARC_PYTHON to a python.exe path."
}

function Resolve-CryptoArcPackageManager {
  $root = Get-CryptoArcRoot
  $npmPath = Resolve-ExistingPath @(
    $env:CRYPTOARC_NPM,
    "C:\Program Files\nodejs\npm.cmd"
  )
  if ($npmPath) {
    return @{ Name = "npm"; FilePath = $npmPath }
  }

  $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
  if ($npmCommand) {
    return @{ Name = "npm"; FilePath = $npmCommand.Source }
  }

  $npmCmdCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
  if ($npmCmdCommand) {
    return @{ Name = "npm"; FilePath = $npmCmdCommand.Source }
  }

  $pnpmPath = Resolve-ExistingPath @(
    $env:CRYPTOARC_PNPM,
    "C:\Users\Ari Rosner\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd"
  )
  if ($pnpmPath) {
    return @{ Name = "pnpm"; FilePath = $pnpmPath }
  }

  $pnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue
  if ($pnpmCommand) {
    return @{ Name = "pnpm"; FilePath = $pnpmCommand.Source }
  }

  $pnpmCmdCommand = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
  if ($pnpmCmdCommand) {
    return @{ Name = "pnpm"; FilePath = $pnpmCmdCommand.Source }
  }

  throw "JavaScript package manager not found. Install Node.js/npm, set CRYPTOARC_NPM to npm.cmd, or set CRYPTOARC_PNPM to pnpm.cmd."
}

function Resolve-CryptoArcNpm {
  $manager = Resolve-CryptoArcPackageManager
  return $manager.FilePath
}

function Get-CryptoArcFrontendInstallArguments {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$PackageManager,
    [switch]$CleanInstall
  )

  if ($PackageManager.Name -eq "pnpm") {
    return @("install", "--no-frozen-lockfile", "--lockfile=false")
  }

  if ($CleanInstall) {
    return @("ci")
  }

  return @("install")
}

function Assert-CryptoArcFrontendDependencies {
  $root = Get-CryptoArcRoot
  $nodeModules = Join-Path $root "frontend\node_modules"
  if (-not (Test-Path -LiteralPath $nodeModules)) {
    throw "frontend\node_modules is missing. Run scripts\bootstrap.ps1 or run npm install in frontend."
  }
}

function Invoke-CryptoArcNative {
  param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,
    [string[]]$Arguments = @()
  )

  & $FilePath @Arguments
  $exitCode = $LASTEXITCODE
  if ($null -ne $exitCode -and $exitCode -ne 0) {
    throw "Command failed with exit code ${exitCode}: $FilePath $($Arguments -join ' ')"
  }
}

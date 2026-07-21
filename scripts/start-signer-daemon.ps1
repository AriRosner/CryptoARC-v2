param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8799,
  [string]$AuthToken = "",
  [double]$MaxTradeSol = 0.001,
  [switch]$AllowSubmit
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runtime.ps1")

$root = Split-Path -Parent $PSScriptRoot
$logsRoot = Join-Path $root "data\logs"
$logPath = Join-Path $logsRoot "signer-daemon.log"
$errPath = Join-Path $logsRoot "signer-daemon.err.log"
$python = Resolve-CryptoArcPython

New-Item -ItemType Directory -Force $logsRoot | Out-Null

if ($HostName -notin @("127.0.0.1", "localhost")) {
  throw "Signer daemon must bind localhost-only."
}

$effectiveAuthToken = if ($AuthToken) { $AuthToken.Trim() } else { ([string]$env:CRYPTOARC_SIGNER_AUTH_TOKEN).Trim() }
$hasConfiguredKey = -not [string]::IsNullOrWhiteSpace([string]$env:CRYPTOARC_SIGNER_PRIVATE_KEY)
if (($hasConfiguredKey -or $AllowSubmit) -and $effectiveAuthToken.Length -lt 32) {
  throw "A configured signer key or AllowSubmit requires a signer auth token of at least 32 characters."
}

if (-not $env:CRYPTOARC_SIGNER_PRIVATE_KEY) {
  Write-Host "CRYPTOARC_SIGNER_PRIVATE_KEY is not set; daemon will start unhealthy and cannot sign." -ForegroundColor Yellow
}

if ($effectiveAuthToken) {
  $env:CRYPTOARC_SIGNER_AUTH_TOKEN = $effectiveAuthToken
}
$env:CRYPTOARC_SIGNER_HOST = $HostName
$env:CRYPTOARC_SIGNER_PORT = [string]$Port
$env:CRYPTOARC_SIGNER_MAX_TRADE_SOL = [string]$MaxTradeSol
$env:CRYPTOARC_SIGNER_ALLOW_SUBMIT = if ($AllowSubmit) { "true" } else { "false" }

$existing = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -ne 0 })
if ($existing.Count -gt 0) {
  throw "Port $Port is already in use. Stop the existing signer daemon or choose a different port."
}

$process = Start-Process `
  -FilePath $python `
  -ArgumentList @("-m", "tools.local_signer_daemon", "--host", $HostName, "--port", [string]$Port) `
  -WorkingDirectory $root `
  -RedirectStandardOutput $logPath `
  -RedirectStandardError $errPath `
  -WindowStyle Hidden `
  -PassThru

$healthUrl = "http://$HostName`:$Port/health"
$healthHeaders = @{}
if ($effectiveAuthToken) {
  $healthHeaders = @{ "Authorization" = "Bearer $effectiveAuthToken" }
}
$healthDeadline = (Get-Date).AddSeconds(10)
$healthReady = $false
try {
  do {
    $process.Refresh()
    if ($process.HasExited) {
      throw "Signer daemon process exited before its health endpoint became ready."
    }
    try {
      $health = Invoke-RestMethod -UseBasicParsing -Uri $healthUrl -Headers $healthHeaders -Method Get -TimeoutSec 2
      $readyToSubmit = $health.ready_to_submit -is [bool] -and $health.ready_to_submit -eq $true
      if ($health.mode -eq "local_signer_daemon" -and (-not $AllowSubmit -or $readyToSubmit)) {
        $healthReady = $true
        break
      }
    } catch {
    }
    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $healthDeadline)

  $process.Refresh()
  if ($process.HasExited) {
    throw "Signer daemon process exited during startup verification."
  }
  if (-not $healthReady) {
    if ($AllowSubmit) {
      throw "Signer daemon did not report ready_to_submit=true within 10 seconds."
    }
    throw "Signer daemon health endpoint did not become ready within 10 seconds."
  }
} catch {
  $process.Refresh()
  if (-not $process.HasExited) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
  }
  throw
}

Write-Host "Signer daemon started on http://$HostName`:$Port with PID $($process.Id)." -ForegroundColor Green
Write-Host "Submit mode: $($AllowSubmit.IsPresent). Health check: scripts\check-signer-daemon.ps1 -Url http://$HostName`:$Port" -ForegroundColor Cyan

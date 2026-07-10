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

if (-not $env:CRYPTOARC_SIGNER_PRIVATE_KEY) {
  Write-Host "CRYPTOARC_SIGNER_PRIVATE_KEY is not set; daemon will start unhealthy and cannot sign." -ForegroundColor Yellow
}

if ($AuthToken) {
  $env:CRYPTOARC_SIGNER_AUTH_TOKEN = $AuthToken
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

Write-Host "Signer daemon started on http://$HostName`:$Port with PID $($process.Id)." -ForegroundColor Green
Write-Host "Submit mode: $($AllowSubmit.IsPresent). Health check: scripts\check-signer-daemon.ps1 -Url http://$HostName`:$Port" -ForegroundColor Cyan

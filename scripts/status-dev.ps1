$ErrorActionPreference = "SilentlyContinue"

$root = Split-Path -Parent $PSScriptRoot
$portsPath = Join-Path $root "data\logs\dev-ports.json"
$backend_port = 8000
$frontend_port = 5173
$backend_url = "http://127.0.0.1:$backend_port"
$frontend_url = "http://127.0.0.1:$frontend_port"
if (Test-Path -LiteralPath $portsPath) {
  try {
    $portReport = Get-Content -LiteralPath $portsPath -Raw | ConvertFrom-Json
    if ($portReport.backend_port) { $backend_port = [int]$portReport.backend_port }
    if ($portReport.frontend_port) { $frontend_port = [int]$portReport.frontend_port }
    if ($portReport.backend_url) { $backend_url = [string]$portReport.backend_url } else { $backend_url = "http://127.0.0.1:$backend_port" }
    if ($portReport.frontend_url) { $frontend_url = [string]$portReport.frontend_url } else { $frontend_url = "http://127.0.0.1:$frontend_port" }
  } catch {
  }
}

Write-Host "Ports"
$ports = @($backend_port, $frontend_port) | Select-Object -Unique
Get-NetTCPConnection -LocalPort $ports |
  Where-Object { $_.OwningProcess -ne 0 } |
  Select-Object LocalPort, OwningProcess, State |
  Format-Table -AutoSize

Write-Host "Configured URLs"
Write-Host "Backend: $backend_url"
Write-Host "Frontend: $frontend_url"

Write-Host "Backend health"
try {
  (Invoke-WebRequest -UseBasicParsing "$backend_url/health/deep").Content
} catch {
  $_.Exception.Message
}

Write-Host "Frontend health"
try {
  (Invoke-WebRequest -UseBasicParsing $frontend_url).StatusCode
} catch {
  $_.Exception.Message
}

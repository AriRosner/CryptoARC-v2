$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "stop-dev.ps1")
Start-Sleep -Seconds 2
& (Join-Path $PSScriptRoot "start-dev.ps1")

try {
  Invoke-WebRequest -UseBasicParsing -Method Post http://127.0.0.1:8000/api/start | Out-Null
  Write-Host "Paper bot started."
} catch {
  Write-Warning "Servers started, but bot start failed: $($_.Exception.Message)"
}

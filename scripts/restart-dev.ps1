$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "stop-dev.ps1")
Start-Sleep -Seconds 2
& (Join-Path $PSScriptRoot "start-dev.ps1")
Write-Host "CryptoARC dev servers restarted in verbose mode."
Write-Host "Bot state remains stopped after restart until you explicitly start it."

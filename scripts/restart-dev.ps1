param(
  [switch]$VerboseMode
)

$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "stop-dev.ps1")
Start-Sleep -Seconds 2
if ($VerboseMode) {
  & (Join-Path $PSScriptRoot "start-dev.ps1") -VerboseMode
  Write-Host "CryptoARC dev servers restarted in verbose mode."
} else {
  & (Join-Path $PSScriptRoot "start-dev.ps1")
  Write-Host "CryptoARC dev servers restarted."
}
Write-Host "Bot state remains stopped after restart until you explicitly start it."

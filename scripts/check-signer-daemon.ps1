param(
  [string]$Url = "http://127.0.0.1:8799",
  [string]$AuthToken = ""
)

$ErrorActionPreference = "Stop"

if (-not $AuthToken -and $env:CRYPTOARC_SIGNER_AUTH_TOKEN) {
  $AuthToken = $env:CRYPTOARC_SIGNER_AUTH_TOKEN
}

$headers = @{}
if ($AuthToken) {
  $headers["Authorization"] = "Bearer $AuthToken"
}

$healthUrl = $Url.TrimEnd("/") + "/health"
$health = Invoke-RestMethod -UseBasicParsing -Uri $healthUrl -Headers $headers -Method Get

Write-Host "Signer daemon health: $($health.mode) / connected=$($health.connected) / healthy=$($health.healthy)" -ForegroundColor Cyan
Write-Host "Wallet: $($health.wallet_public_key)" -ForegroundColor Cyan
Write-Host "Can sign: $($health.can_sign) / unattended: $($health.can_unattended_sign)" -ForegroundColor Cyan
Write-Host "Submit enabled: $($health.policy.allow_submit) / max trade SOL: $($health.policy.max_trade_sol)" -ForegroundColor Cyan

if (-not $health.healthy -or -not $health.can_sign) {
  throw "Signer daemon is reachable but not ready to sign."
}

Write-Host "No-trade signer daemon check passed." -ForegroundColor Green

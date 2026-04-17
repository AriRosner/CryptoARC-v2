$ErrorActionPreference = "SilentlyContinue"

Write-Host "Ports"
Get-NetTCPConnection -LocalPort 8000, 5173 |
  Where-Object { $_.OwningProcess -ne 0 } |
  Select-Object LocalPort, OwningProcess, State |
  Format-Table -AutoSize

Write-Host "Backend health"
try {
  (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health/deep).Content
} catch {
  $_.Exception.Message
}

Write-Host "Frontend health"
try {
  (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173).StatusCode
} catch {
  $_.Exception.Message
}

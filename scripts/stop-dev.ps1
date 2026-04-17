$ErrorActionPreference = "SilentlyContinue"

$ports = 8000, 5173
foreach ($port in $ports) {
  Get-NetTCPConnection -LocalPort $port |
    Where-Object { $_.OwningProcess -ne 0 } |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force }
}

Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -and (
      $_.CommandLine -like "*uvicorn app.main:app*" -or
      $_.CommandLine -like "*npm.cmd*run dev*" -or
      $_.CommandLine -like "*vite*--host 127.0.0.1*"
    )
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "CryptoARC dev processes stopped."

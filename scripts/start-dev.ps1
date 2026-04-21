$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendCommand = @"
Set-Location '$root'
\$env:PYTHONPATH = 'backend'
Write-Host 'CryptoARC backend starting in verbose mode...' -ForegroundColor Cyan
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --log-level debug
"@

$frontendRoot = Join-Path $root "frontend"
$frontendCommand = @"
Set-Location '$frontendRoot'
\$env:PATH = 'C:\Program Files\nodejs;' + \$env:PATH
Write-Host 'CryptoARC frontend starting in verbose mode...' -ForegroundColor Magenta
& 'C:\Program Files\nodejs\npm.cmd' run dev -- --host 127.0.0.1 --port 5173 --debug
"@

Start-Process -FilePath powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) | Out-Null
Start-Process -FilePath powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand) | Out-Null

Start-Sleep -Seconds 5
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health | Out-Null
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173 | Out-Null
Write-Host "CryptoARC dev servers running in verbose mode."
Write-Host "Bot state remains stopped until you explicitly start it from the dashboard or API."

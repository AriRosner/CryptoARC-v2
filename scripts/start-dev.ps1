$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$backendArgs = '/c "cd /d ' + $root + ' && set PYTHONPATH=backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > data\logs\backend-dev.log 2>&1"'
$frontendArgs = '/c "cd /d ' + (Join-Path $root "frontend") + ' && set PATH=C:\Program Files\nodejs;%PATH% && "C:\Program Files\nodejs\npm.cmd" run dev -- --host 127.0.0.1 --port 5173 > ..\data\logs\frontend-dev.log 2>&1"'

Start-Process -FilePath cmd.exe -WindowStyle Hidden -ArgumentList $backendArgs | Out-Null
Start-Process -FilePath cmd.exe -WindowStyle Hidden -ArgumentList $frontendArgs | Out-Null

Start-Sleep -Seconds 5
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health | Out-Null
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173 | Out-Null
Write-Host "CryptoARC dev servers running."

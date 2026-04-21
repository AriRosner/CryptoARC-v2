param(
  [switch]$VerboseMode
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $root "frontend"
$logsRoot = Join-Path $root "data\logs"

function Wait-HttpReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [int]$TimeoutSeconds = 30
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      Invoke-WebRequest -UseBasicParsing $Url | Out-Null
      return
    } catch {
      Start-Sleep -Milliseconds 750
    }
  } while ((Get-Date) -lt $deadline)

  throw "$Name did not become ready within $TimeoutSeconds seconds at $Url."
}

if (-not (Test-Path $logsRoot)) {
  New-Item -ItemType Directory -Path $logsRoot | Out-Null
}

if ($VerboseMode) {
  $backendCommand = @"
Set-Location '$root'
\$env:PYTHONPATH = 'backend'
Write-Host 'CryptoARC backend starting in verbose mode...' -ForegroundColor Cyan
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --log-level debug
"@

  $frontendCommand = @"
Set-Location '$frontendRoot'
\$env:PATH = 'C:\Program Files\nodejs;' + \$env:PATH
Write-Host 'CryptoARC frontend starting in verbose mode...' -ForegroundColor Magenta
& 'C:\Program Files\nodejs\npm.cmd' run dev -- --host 127.0.0.1 --port 5173 --debug
"@

  Start-Process -FilePath powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) | Out-Null
  Start-Process -FilePath powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand) | Out-Null
} else {
  $backendLog = Join-Path $logsRoot "backend-dev.log"
  $frontendLog = Join-Path $logsRoot "frontend-dev.log"
  $backendCommand = "cd /d ""$root"" && set PYTHONPATH=backend && .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --log-level debug >> ""$backendLog"" 2>&1"
  $frontendCommand = "cd /d ""$frontendRoot"" && set PATH=C:\Program Files\nodejs;%PATH% && ""C:\Program Files\nodejs\npm.cmd"" run dev -- --host 127.0.0.1 --port 5173 >> ""$frontendLog"" 2>&1"

  Start-Process -WindowStyle Hidden -FilePath cmd.exe -ArgumentList @("/c", $backendCommand) | Out-Null
  Start-Process -WindowStyle Hidden -FilePath cmd.exe -ArgumentList @("/c", $frontendCommand) | Out-Null
}

try {
  Wait-HttpReady -Url "http://127.0.0.1:8000/health" -Name "Backend"
  Wait-HttpReady -Url "http://127.0.0.1:5173" -Name "Frontend"
} catch {
  if (-not $VerboseMode) {
    if (Test-Path $backendLog) {
      Write-Host ""
      Write-Host "Last backend log lines:" -ForegroundColor Yellow
      Get-Content $backendLog -Tail 20
    }
    if (Test-Path $frontendLog) {
      Write-Host ""
      Write-Host "Last frontend log lines:" -ForegroundColor Yellow
      Get-Content $frontendLog -Tail 20
    }
  }
  throw
}

if ($VerboseMode) {
  Write-Host "CryptoARC dev servers running in verbose mode."
} else {
  Write-Host "CryptoARC dev servers running. Logs: $logsRoot"
}
Write-Host "Bot state remains stopped until you explicitly start it from the dashboard or API."

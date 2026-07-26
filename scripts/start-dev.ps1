param(
  [switch]$VerboseMode
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runtime.ps1")

$root = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $root "frontend"
$logsRoot = Join-Path $root "data\logs"
$portsPath = Join-Path $logsRoot "dev-ports.json"
$processesPath = Join-Path $logsRoot "dev-processes.json"
$python = Resolve-CryptoArcPython
$backendExecutable = [System.IO.Path]::GetFullPath($python).TrimEnd("\", "/")
$backendBaseExecutableOutput = @(& $python -c "import sys; print(sys._base_executable)")
if (
  $LASTEXITCODE -ne 0 -or
  $backendBaseExecutableOutput.Count -ne 1 -or
  [string]::IsNullOrWhiteSpace([string]$backendBaseExecutableOutput[0])
) {
  throw "Could not resolve the selected Python runtime base executable."
}
$backendBaseExecutable = [System.IO.Path]::GetFullPath(
  [string]$backendBaseExecutableOutput[0]
).TrimEnd("\", "/")
$packageManager = Resolve-CryptoArcPackageManager
$packageManagerPath = $packageManager.FilePath
Assert-CryptoArcFrontendDependencies

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

function Test-CryptoArcPortAvailable {
  param(
    [Parameter(Mandatory = $true)]
    [int]$Port
  )

  $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -ne 0 })
  return $listeners.Count -eq 0
}

function Resolve-CryptoArcDevPort {
  param(
    [Parameter(Mandatory = $true)]
    [int]$PreferredPort,
    [Parameter(Mandatory = $true)]
    [string]$Name
  )

  if (Test-CryptoArcPortAvailable -Port $PreferredPort) {
    return $PreferredPort
  }

  for ($port = $PreferredPort + 1; $port -le $PreferredPort + 99; $port++) {
    if (Test-CryptoArcPortAvailable -Port $port) {
      Write-Host "$Name port $PreferredPort is busy; using $port instead." -ForegroundColor Yellow
      return $port
    }
  }

  throw "No free local port found for $Name near $PreferredPort."
}

function Get-CryptoArcChildProcessIds {
  param(
    [int[]]$ParentIds
  )

  if (-not $ParentIds -or $ParentIds.Count -eq 0) {
    return @()
  }

  $children = @()
  foreach ($parentId in $ParentIds) {
    $children += Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        $_.ParentProcessId -eq $parentId -and
        $_.CommandLine -and
        ($_.CommandLine -like "*multiprocessing-fork*" -or $_.CommandLine -like "*uvicorn*app.main:app*")
      } |
      Select-Object -ExpandProperty ProcessId
  }
  return @($children | Select-Object -Unique)
}

function Get-CryptoArcPortOwnerProcessIds {
  param(
    [int]$Port
  )

  return @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Where-Object { $_.OwningProcess -ne 0 } |
      Select-Object -ExpandProperty OwningProcess -Unique
  )
}

function Write-CryptoArcProcessManifest {
  param(
    [int]$BackendLauncherPid,
    [int]$FrontendLauncherPid
  )

  $backendChildPids = Get-CryptoArcChildProcessIds -ParentIds @($BackendLauncherPid)
  $backendPortOwnerPids = Get-CryptoArcPortOwnerProcessIds -Port $backendPort
  $frontendPortOwnerPids = Get-CryptoArcPortOwnerProcessIds -Port $frontendPort
  $processReport = [ordered]@{
    backend_launcher_pid = $BackendLauncherPid
    frontend_launcher_pid = $FrontendLauncherPid
    backend_child_pids = @($backendChildPids)
    backend_port_owner_pids = @($backendPortOwnerPids)
    frontend_port_owner_pids = @($frontendPortOwnerPids)
    backend_executable = $backendExecutable
    backend_base_executable = $backendBaseExecutable
    backend_port = $backendPort
    frontend_port = $frontendPort
    backend_url = $backendUrl
    frontend_url = $frontendUrl
    root = $root
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  $processReport | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $processesPath -Encoding UTF8
}

if (-not (Test-Path $logsRoot)) {
  New-Item -ItemType Directory -Path $logsRoot | Out-Null
}

$backendPort = Resolve-CryptoArcDevPort -PreferredPort 8000 -Name "Backend"
$frontendPort = Resolve-CryptoArcDevPort -PreferredPort 5173 -Name "Frontend"
$backendUrl = "http://127.0.0.1:$backendPort"
$frontendUrl = "http://127.0.0.1:$frontendPort"
$portReport = [ordered]@{
  backend_port = $backendPort
  frontend_port = $frontendPort
  backend_url = $backendUrl
  frontend_url = $frontendUrl
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
}
$portReport | ConvertTo-Json | Set-Content -LiteralPath $portsPath -Encoding UTF8

if ($VerboseMode) {
  $backendCommand = @"
Set-Location '$root'
\$env:PYTHONPATH = 'backend'
Write-Host 'CryptoARC backend starting in verbose mode...' -ForegroundColor Cyan
& '$python' -m uvicorn app.main:app --host 127.0.0.1 --port $backendPort --reload --log-level debug
"@

  $frontendCommand = @"
Set-Location '$frontendRoot'
\$env:VITE_API_BASE_URL = '$backendUrl'
Write-Host 'CryptoARC frontend starting in verbose mode...' -ForegroundColor Magenta
& '$packageManagerPath' run dev -- --host 127.0.0.1 --port $frontendPort --strictPort --debug
"@

  $backendProcess = Start-Process -FilePath powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) -PassThru
  $frontendProcess = Start-Process -FilePath powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand) -PassThru
} else {
  $backendLog = Join-Path $logsRoot "backend-dev.log"
  $frontendLog = Join-Path $logsRoot "frontend-dev.log"
  $backendCommand = "Set-Location '$root'; `$env:PYTHONPATH = 'backend'; & '$python' -m uvicorn app.main:app --host 127.0.0.1 --port $backendPort --reload --log-level debug *> '$backendLog'"
  $frontendCommand = "Set-Location '$frontendRoot'; `$env:VITE_API_BASE_URL = '$backendUrl'; & '$packageManagerPath' run dev -- --host 127.0.0.1 --port $frontendPort --strictPort *> '$frontendLog'"

  $backendProcess = Start-Process -WindowStyle Hidden -FilePath powershell.exe -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) -PassThru
  $frontendProcess = Start-Process -WindowStyle Hidden -FilePath powershell.exe -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand) -PassThru
}

Write-CryptoArcProcessManifest -BackendLauncherPid $backendProcess.Id -FrontendLauncherPid $frontendProcess.Id

try {
  Wait-HttpReady -Url "$backendUrl/health" -Name "Backend"
  Wait-HttpReady -Url $frontendUrl -Name "Frontend"
  Write-CryptoArcProcessManifest -BackendLauncherPid $backendProcess.Id -FrontendLauncherPid $frontendProcess.Id
} catch {
  Write-CryptoArcProcessManifest -BackendLauncherPid $backendProcess.Id -FrontendLauncherPid $frontendProcess.Id
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
Write-Host "Backend: $backendUrl"
Write-Host "Frontend: $frontendUrl"
Write-Host "Bot state remains stopped until you explicitly start it from the dashboard or API."

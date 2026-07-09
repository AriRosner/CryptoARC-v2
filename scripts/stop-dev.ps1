$ErrorActionPreference = "SilentlyContinue"

$root = Split-Path -Parent $PSScriptRoot
$logsRoot = Join-Path $root "data\logs"
$portsPath = Join-Path $logsRoot "dev-ports.json"
$processesPath = Join-Path $logsRoot "dev-processes.json"
$defaultBackendPorts = @(8000..8010)
$defaultFrontendPorts = @(5173..5180)
$ports = New-Object System.Collections.Generic.List[int]

function Add-CryptoArcPort {
  param([int]$Port)
  if (-not $ports.Contains($Port)) {
    $ports.Add($Port) | Out-Null
  }
}

function Get-CryptoArcPortOwners {
  param([int[]]$Ports)

  $owners = @()
  foreach ($port in $Ports) {
    Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
      Where-Object { $_.OwningProcess -ne 0 } |
      Select-Object -ExpandProperty OwningProcess -Unique |
      ForEach-Object { $owners += [int]$_ }
  }
  return @($owners | Select-Object -Unique)
}

function Get-CryptoArcDescendantProcessIds {
  param([int[]]$ParentIds)

  $seen = New-Object System.Collections.Generic.HashSet[int]
  $queue = New-Object System.Collections.Generic.Queue[int]
  foreach ($parentId in $ParentIds) {
    if ($parentId -gt 0 -and $seen.Add($parentId)) {
      $queue.Enqueue($parentId)
    }
  }

  while ($queue.Count -gt 0) {
    $current = $queue.Dequeue()
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object { $_.ParentProcessId -eq $current } |
      ForEach-Object {
        $childId = [int]$_.ProcessId
        if ($seen.Add($childId)) {
          $queue.Enqueue($childId)
        }
      }
  }

  return @($seen)
}

function Stop-CryptoArcProcessTree {
  param([int[]]$ProcessIds)

  $allIds = Get-CryptoArcDescendantProcessIds -ParentIds $ProcessIds
  foreach ($processId in ($allIds | Sort-Object -Descending)) {
    if ($processId -le 0) {
      continue
    }
    & taskkill.exe /PID $processId /F /T *> $null
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
  }
}

function Stop-CryptoArcBackendsByApi {
  param([int[]]$Ports)

  foreach ($port in $Ports) {
    try {
      Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/stop" -Method Post -TimeoutSec 3 | Out-Null
    } catch {
    }
  }
}

function Get-CryptoArcWorkspaceProcessIds {
  $workspace = $root.Replace("\", "\\")
  $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and (
        ($_.CommandLine -like "*$root*" -and (
          $_.CommandLine -like "*uvicorn app.main:app*" -or
          $_.CommandLine -like "*npm*run dev*" -or
          $_.CommandLine -like "*vite*--host 127.0.0.1*"
        )) -or
        ($_.CommandLine -like "*multiprocessing-fork*" -and $_.CommandLine -match "parent_pid=")
      )
    }
  return @($processes | Select-Object -ExpandProperty ProcessId -Unique)
}

function Get-CryptoArcForkChildProcessIds {
  param([int[]]$ParentIds)

  $children = @()
  foreach ($parentId in $ParentIds) {
    $children += Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        $_.CommandLine -and
        $_.CommandLine -like "*multiprocessing-fork*" -and
        ($_.ParentProcessId -eq $parentId -or $_.CommandLine -like "*parent_pid=$parentId,*" -or $_.CommandLine -like "*parent_pid=$parentId *")
      } |
      Select-Object -ExpandProperty ProcessId
  }
  return @($children | Select-Object -Unique)
}

function Assert-CryptoArcDevPortsStopped {
  param([int[]]$Ports)

  $stillListening = @()
  foreach ($port in $Ports) {
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -ne 0 })
    foreach ($listener in $listeners) {
      try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/health" -TimeoutSec 2 | Out-Null
        $stillListening += "$port/$($listener.OwningProcess)"
      } catch {
      }
    }
  }

  if ($stillListening.Count -gt 0) {
    Write-Warning "CryptoARC dev ports still answer /health: $($stillListening -join ', ')"
  }
}

foreach ($port in $defaultBackendPorts + $defaultFrontendPorts) {
  Add-CryptoArcPort -Port $port
}

if (Test-Path -LiteralPath $portsPath) {
  try {
    $portReport = Get-Content -LiteralPath $portsPath -Raw | ConvertFrom-Json
    if ($portReport.backend_port) { Add-CryptoArcPort -Port ([int]$portReport.backend_port) }
    if ($portReport.frontend_port) { Add-CryptoArcPort -Port ([int]$portReport.frontend_port) }
  } catch {
  }
}

$manifestProcessIds = @()
if (Test-Path -LiteralPath $processesPath) {
  try {
    $processReport = Get-Content -LiteralPath $processesPath -Raw | ConvertFrom-Json
    foreach ($field in @("backend_launcher_pid", "frontend_launcher_pid")) {
      if ($processReport.$field) {
        $manifestProcessIds += [int]$processReport.$field
      }
    }
    foreach ($childId in @($processReport.backend_child_pids)) {
      if ($childId) {
        $manifestProcessIds += [int]$childId
      }
    }
    foreach ($ownerId in @($processReport.backend_port_owner_pids) + @($processReport.frontend_port_owner_pids)) {
      if ($ownerId) {
        $manifestProcessIds += [int]$ownerId
      }
    }
  } catch {
  }
}

Stop-CryptoArcBackendsByApi -Ports $defaultBackendPorts
Start-Sleep -Milliseconds 750

$portOwnerIds = Get-CryptoArcPortOwners -Ports @($ports)
$forkChildIds = Get-CryptoArcForkChildProcessIds -ParentIds $portOwnerIds
$workspaceProcessIds = Get-CryptoArcWorkspaceProcessIds
$processIds = @($manifestProcessIds + $portOwnerIds + $forkChildIds + $workspaceProcessIds) | Where-Object { $_ -gt 0 } | Select-Object -Unique
Stop-CryptoArcProcessTree -ProcessIds $processIds

Start-Sleep -Seconds 2
Assert-CryptoArcDevPortsStopped -Ports @($ports)

if (Test-Path -LiteralPath $portsPath) {
  Remove-Item -LiteralPath $portsPath -Force
}
if (Test-Path -LiteralPath $processesPath) {
  Remove-Item -LiteralPath $processesPath -Force
}

Write-Host "CryptoARC dev processes stopped."

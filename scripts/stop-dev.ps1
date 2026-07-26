$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logsRoot = Join-Path $root "data\logs"
$portsPath = Join-Path $logsRoot "dev-ports.json"
$processesPath = Join-Path $logsRoot "dev-processes.json"
$processReport = $null

function Get-NormalizedCryptoArcPath {
  param([Parameter(Mandatory = $true)][string]$Path)

  return [System.IO.Path]::GetFullPath($Path).TrimEnd("\", "/")
}

function ConvertTo-CryptoArcPort {
  param(
    [object]$Value,
    [string]$Name
  )

  $port = 0
  if (-not [int]::TryParse([string]$Value, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
    throw "Invalid $Name in CryptoARC dev manifest."
  }
  return $port
}

function ConvertTo-CryptoArcManifestTimestamp {
  param(
    [object]$Value,
    [string]$Name
  )

  $timestamp = [DateTimeOffset]::MinValue
  if (
    -not $Value -or
    -not [DateTimeOffset]::TryParseExact(
      [string]$Value,
      "o",
      [System.Globalization.CultureInfo]::InvariantCulture,
      [System.Globalization.DateTimeStyles]::RoundtripKind,
      [ref]$timestamp
    ) -or
    $timestamp.Offset -ne [TimeSpan]::Zero -or
    $timestamp -gt [DateTimeOffset]::UtcNow
  ) {
    throw "Invalid $Name in CryptoARC process manifest."
  }
  return $timestamp
}

function Test-CryptoArcManifestProcessFreshness {
  param(
    [object]$Process,
    [DateTimeOffset]$ManifestGeneratedAt
  )

  if ($null -eq $Process.CreationDate) {
    return $false
  }
  try {
    if ($Process.CreationDate -is [DateTimeOffset]) {
      $createdAt = [DateTimeOffset]$Process.CreationDate
    } elseif ($Process.CreationDate -is [DateTime]) {
      $createdAt = [DateTimeOffset]([DateTime]$Process.CreationDate)
    } else {
      $createdAt = [DateTimeOffset]::MinValue
      if (
        -not [DateTimeOffset]::TryParse(
          [string]$Process.CreationDate,
          [System.Globalization.CultureInfo]::InvariantCulture,
          (
            [System.Globalization.DateTimeStyles]::AssumeUniversal -bor
            [System.Globalization.DateTimeStyles]::AdjustToUniversal
          ),
          [ref]$createdAt
        )
      ) {
        return $false
      }
    }
    return $createdAt.ToUniversalTime() -le $ManifestGeneratedAt.ToUniversalTime()
  } catch {
    return $false
  }
}

function Test-CryptoArcBackendExecutableIdentity {
  param(
    [object]$Process,
    [string]$ManifestBackendExecutable,
    [string]$ManifestBackendBaseExecutable
  )

  $executable = [string]$Process.ExecutablePath
  if (-not $executable -or -not $ManifestBackendExecutable) {
    return $false
  }
  try {
    $normalizedExecutable = Get-NormalizedCryptoArcPath -Path $executable
    $normalizedRoot = Get-NormalizedCryptoArcPath -Path $root
    $rootPrefix = "$normalizedRoot\"
    if (
      $normalizedExecutable.Equals($normalizedRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
      $normalizedExecutable.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
      return $true
    }
    return (
      $normalizedExecutable.Equals(
        $ManifestBackendExecutable,
        [System.StringComparison]::OrdinalIgnoreCase
      ) -or
      (
        $ManifestBackendBaseExecutable -and
        $normalizedExecutable.Equals(
          $ManifestBackendBaseExecutable,
          [System.StringComparison]::OrdinalIgnoreCase
        )
      )
    )
  } catch {
    return $false
  }
}

function Test-CryptoArcRootIdentity {
  param([object]$Process)

  $normalizedRoot = Get-NormalizedCryptoArcPath -Path $root
  $rootPrefix = "$normalizedRoot\"
  $executable = [string]$Process.ExecutablePath
  if ($executable) {
    try {
      $normalizedExecutable = Get-NormalizedCryptoArcPath -Path $executable
      if (
        $normalizedExecutable.Equals($normalizedRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        $normalizedExecutable.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)
      ) {
        return $true
      }
    } catch {
    }
  }

  $commandLine = [string]$Process.CommandLine
  if (-not $commandLine) {
    return $false
  }
  $escapedRoot = [regex]::Escape($normalizedRoot)
  $boundaryPattern = "(?i)(^|[\s`"'])$escapedRoot(?=$|[\\/\s`"'])"
  return [regex]::IsMatch($commandLine, $boundaryPattern)
}

function Test-CryptoArcLauncherIdentity {
  param([object]$Process)

  if (-not (Test-CryptoArcRootIdentity -Process $Process)) {
    return $false
  }
  $commandLine = [string]$Process.CommandLine
  if (-not $commandLine) {
    return $false
  }
  return (
    $commandLine -match "(?i)(^|\s)-m\s+uvicorn\s+app\.main:app(\s|$)" -or
    $commandLine -match "(?i)uvicorn(?:\.exe)?\s+app\.main:app(\s|$)" -or
    ($commandLine -match "(?i)\brun\s+dev\b" -and $commandLine -match "(?i)--host\s+127\.0\.0\.1") -or
    ($commandLine -match "(?i)(^|[\\/])vite(?:\.js)?(\s|`"|')" -and $commandLine -match "(?i)--host\s+127\.0\.0\.1")
  )
}

function Test-CryptoArcForkChildIdentity {
  param(
    [object]$Process,
    [int[]]$ValidatedParentIds,
    [int[]]$ManifestBackendIds,
    [DateTimeOffset]$ManifestGeneratedAt,
    [string]$ManifestBackendExecutable,
    [string]$ManifestBackendBaseExecutable
  )

  if ([string]$Process.CommandLine -notmatch "(?i)multiprocessing-fork") {
    return $false
  }
  if ($ValidatedParentIds -contains [int]$Process.ParentProcessId) {
    return $true
  }
  return (
    $ManifestBackendIds -contains [int]$Process.ProcessId -and
    (
      Test-CryptoArcBackendExecutableIdentity `
        -Process $Process `
        -ManifestBackendExecutable $ManifestBackendExecutable `
        -ManifestBackendBaseExecutable $ManifestBackendBaseExecutable
    ) -and
    (Test-CryptoArcManifestProcessFreshness -Process $Process -ManifestGeneratedAt $ManifestGeneratedAt)
  )
}

function Test-CryptoArcConflictingWorkspaceIdentity {
  param([object]$Process)

  $executable = [string]$Process.ExecutablePath
  if ($executable -match "(?i)[\\/]\.venv[\\/]" -and -not (Test-CryptoArcRootIdentity -Process $Process)) {
    return $true
  }
  return $false
}

function Test-CryptoArcBackendManifestIdentity {
  param(
    [object]$Process,
    [int[]]$ManifestBackendIds,
    [DateTimeOffset]$ManifestGeneratedAt,
    [string]$ManifestBackendExecutable,
    [string]$ManifestBackendBaseExecutable
  )

  if (
    $ManifestBackendIds -notcontains [int]$Process.ProcessId -or
    -not (
      Test-CryptoArcBackendExecutableIdentity `
        -Process $Process `
        -ManifestBackendExecutable $ManifestBackendExecutable `
        -ManifestBackendBaseExecutable $ManifestBackendBaseExecutable
    ) -or
    -not (Test-CryptoArcManifestProcessFreshness -Process $Process -ManifestGeneratedAt $ManifestGeneratedAt)
  ) {
    return $false
  }
  $commandLine = [string]$Process.CommandLine
  return (
    $commandLine -match "(?i)(^|\s)-m\s+uvicorn\s+app\.main:app(\s|$)" -or
    $commandLine -match "(?i)uvicorn(?:\.exe)?\s+app\.main:app(\s|$)" -or
    $commandLine -match "(?i)multiprocessing-fork"
  )
}

function Test-CryptoArcFrontendManifestIdentity {
  param(
    [object]$Process,
    [int[]]$ManifestFrontendIds,
    [DateTimeOffset]$ManifestGeneratedAt
  )

  if (
    $ManifestFrontendIds -notcontains [int]$Process.ProcessId -or
    (Test-CryptoArcConflictingWorkspaceIdentity -Process $Process) -or
    -not (Test-CryptoArcManifestProcessFreshness -Process $Process -ManifestGeneratedAt $ManifestGeneratedAt)
  ) {
    return $false
  }
  $commandLine = [string]$Process.CommandLine
  return (
    ($commandLine -match "(?i)\brun\s+dev\b" -and $commandLine -match "(?i)--host\s+127\.0\.0\.1") -or
    ($commandLine -match "(?i)(^|[\\/])vite(?:\.js)?(\s|`"|')" -and $commandLine -match "(?i)--host\s+127\.0\.0\.1")
  )
}

function Get-CryptoArcProcessSnapshot {
  try {
    return @(Get-CimInstance Win32_Process -ErrorAction Stop)
  } catch {
    throw "CryptoARC process discovery is unavailable; shutdown is indeterminate. Process manifests were preserved."
  }
}

function Get-CryptoArcBackendPortAuthority {
  param(
    [int]$BackendPort,
    [int[]]$ManifestBackendIds,
    [DateTimeOffset]$ManifestGeneratedAt,
    [string]$ManifestBackendExecutable,
    [string]$ManifestBackendBaseExecutable
  )

  try {
    $ownerIds = @(
      Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object { [int]$_.LocalPort -eq $BackendPort } |
        Where-Object { $_.OwningProcess -ne 0 } |
        Select-Object -ExpandProperty OwningProcess -Unique
    )
    if ($ownerIds.Count -eq 0) {
      return [pscustomobject]@{ State = "clear"; OwnerId = 0 }
    }
    if ($ownerIds.Count -ne 1) {
      return [pscustomobject]@{ State = "unknown"; OwnerId = 0 }
    }
    $snapshot = Get-CryptoArcProcessSnapshot
    $owner = @($snapshot | Where-Object { [int]$_.ProcessId -eq [int]$ownerIds[0] }) |
      Select-Object -First 1
    if (
      -not $owner -or
      -not (
        Test-CryptoArcBackendManifestIdentity `
          -Process $owner `
          -ManifestBackendIds $ManifestBackendIds `
          -ManifestGeneratedAt $ManifestGeneratedAt `
          -ManifestBackendExecutable $ManifestBackendExecutable `
          -ManifestBackendBaseExecutable $ManifestBackendBaseExecutable
      )
    ) {
      return [pscustomobject]@{ State = "unknown"; OwnerId = [int]$ownerIds[0] }
    }
    return [pscustomobject]@{ State = "authorized"; OwnerId = [int]$ownerIds[0] }
  } catch {
    return [pscustomobject]@{ State = "unavailable"; OwnerId = 0 }
  }
}

function Stop-CryptoArcBackendByApi {
  param(
    [int]$BackendPort,
    [object]$Authority
  )

  if (-not $Authority -or $Authority.State -ne "authorized") {
    return
  }

  try {
    Invoke-WebRequest `
      -UseBasicParsing `
      -Uri "http://127.0.0.1:$BackendPort/api/stop" `
      -Method Post `
      -MaximumRedirection 0 `
      -TimeoutSec 1 `
      -ErrorAction Stop | Out-Null
  } catch {
  }
}

function Assert-CryptoArcPidFields {
  param([object]$Report)

  foreach ($field in @("backend_launcher_pid", "frontend_launcher_pid")) {
    if ($null -ne $Report.$field) {
      $pidValue = 0
      if (-not [int]::TryParse([string]$Report.$field, [ref]$pidValue) -or $pidValue -le 0) {
        throw "CryptoARC process manifest has an invalid $field."
      }
    }
  }
  foreach ($field in @("backend_child_pids", "backend_port_owner_pids", "frontend_port_owner_pids")) {
    if ($Report.$field -isnot [System.Array]) {
      throw "CryptoARC process manifest has an invalid $field."
    }
    foreach ($value in @($Report.$field)) {
      $pidValue = 0
      if (-not [int]::TryParse([string]$value, [ref]$pidValue) -or $pidValue -le 0) {
        throw "CryptoARC process manifest has an invalid $field."
      }
    }
  }
}

function Stop-CryptoArcValidatedProcesses {
  param(
    [int[]]$ProcessIds,
    [int[]]$ValidatedParentIds,
    [int[]]$ManifestBackendIds,
    [int[]]$ManifestFrontendIds,
    [DateTimeOffset]$ManifestGeneratedAt,
    [string]$ManifestBackendExecutable,
    [string]$ManifestBackendBaseExecutable
  )

  $attemptedIds = @()
  $failedIds = @()
  foreach ($processId in ($ProcessIds | Sort-Object -Descending -Unique)) {
    if ($processId -le 0) {
      continue
    }
    $current = @(Get-CryptoArcProcessSnapshot | Where-Object { [int]$_.ProcessId -eq $processId }) |
      Select-Object -First 1
    if (
      -not $current -or
      (
        -not (Test-CryptoArcLauncherIdentity -Process $current) -and
        -not (
          Test-CryptoArcBackendManifestIdentity `
            -Process $current `
            -ManifestBackendIds $ManifestBackendIds `
            -ManifestGeneratedAt $ManifestGeneratedAt `
            -ManifestBackendExecutable $ManifestBackendExecutable `
            -ManifestBackendBaseExecutable $ManifestBackendBaseExecutable
        ) -and
        -not (
          Test-CryptoArcFrontendManifestIdentity `
            -Process $current `
            -ManifestFrontendIds $ManifestFrontendIds `
            -ManifestGeneratedAt $ManifestGeneratedAt
        ) -and
        -not (
          Test-CryptoArcForkChildIdentity `
            -Process $current `
            -ValidatedParentIds $ValidatedParentIds `
            -ManifestBackendIds $ManifestBackendIds `
            -ManifestGeneratedAt $ManifestGeneratedAt `
            -ManifestBackendExecutable $ManifestBackendExecutable `
            -ManifestBackendBaseExecutable $ManifestBackendBaseExecutable
        )
      )
    ) {
      continue
    }
    $attemptedIds += $processId
    $global:LASTEXITCODE = 0
    & taskkill.exe /PID $processId /F *> $null
    if ($LASTEXITCODE -ne 0) {
      $failedIds += $processId
    }
  }

  $survivorIds = @()
  foreach ($processId in $attemptedIds) {
    $current = @(Get-CryptoArcProcessSnapshot | Where-Object { [int]$_.ProcessId -eq $processId }) |
      Select-Object -First 1
    if (
      $current -and
      (
        (Test-CryptoArcLauncherIdentity -Process $current) -or
        (
          Test-CryptoArcBackendManifestIdentity `
            -Process $current `
            -ManifestBackendIds $ManifestBackendIds `
            -ManifestGeneratedAt $ManifestGeneratedAt `
            -ManifestBackendExecutable $ManifestBackendExecutable `
            -ManifestBackendBaseExecutable $ManifestBackendBaseExecutable
        ) -or
        (
          Test-CryptoArcFrontendManifestIdentity `
            -Process $current `
            -ManifestFrontendIds $ManifestFrontendIds `
            -ManifestGeneratedAt $ManifestGeneratedAt
        ) -or
        (
          Test-CryptoArcForkChildIdentity `
            -Process $current `
            -ValidatedParentIds $ValidatedParentIds `
            -ManifestBackendIds $ManifestBackendIds `
            -ManifestGeneratedAt $ManifestGeneratedAt `
            -ManifestBackendExecutable $ManifestBackendExecutable `
            -ManifestBackendBaseExecutable $ManifestBackendBaseExecutable
        )
      )
    ) {
      $survivorIds += $processId
    }
  }
  if ($survivorIds.Count -gt 0) {
    $failedSurvivors = @($survivorIds | Where-Object { $failedIds -contains $_ })
    if ($failedSurvivors.Count -gt 0) {
      throw "taskkill reported failure and the CryptoARC process remained live. Process manifests were preserved."
    }
    throw "CryptoARC process remained live after termination. Process manifests were preserved."
  }
}

function Remove-CryptoArcManifest {
  param([string]$Path)

  if (Test-Path -LiteralPath $Path) {
    Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
  }
  if (Test-Path -LiteralPath $Path) {
    throw "Failed to remove CryptoARC dev manifest at $Path."
  }
}

$root = Get-NormalizedCryptoArcPath -Path $root
$portsExists = Test-Path -LiteralPath $portsPath
$processesExists = Test-Path -LiteralPath $processesPath
$manifestErrors = @()
$manifestBackendIds = @()
$manifestFrontendIds = @()
$manifestGeneratedAt = [DateTimeOffset]::MinValue
$manifestBackendExecutable = $null
$manifestBackendBaseExecutable = $null
$portsManifestValid = $false
$processManifestValid = $false
if ($portsExists) {
  try {
    $portReport = Get-Content -LiteralPath $portsPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    $backendPort = ConvertTo-CryptoArcPort -Value $portReport.backend_port -Name "backend_port"
    $frontendPort = ConvertTo-CryptoArcPort -Value $portReport.frontend_port -Name "frontend_port"
    $recordedBackendPort = $backendPort
    $portsManifestValid = $true
  } catch {
    $manifestErrors += "CryptoARC ports manifest is malformed."
  }
}

if ($processesExists) {
  try {
    $processReport = Get-Content -LiteralPath $processesPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    $requiredProcessFields = @(
      "root",
      "backend_port",
      "frontend_port",
      "backend_launcher_pid",
      "frontend_launcher_pid",
      "backend_child_pids",
      "backend_port_owner_pids",
      "frontend_port_owner_pids",
      "backend_executable",
      "generated_at"
    )
    foreach ($field in $requiredProcessFields) {
      if ($processReport.PSObject.Properties.Name -notcontains $field) {
        throw "CryptoARC process manifest is missing $field."
      }
    }
    Assert-CryptoArcPidFields -Report $processReport
    $manifestGeneratedAt = ConvertTo-CryptoArcManifestTimestamp `
      -Value $processReport.generated_at `
      -Name "generated_at"
    if (
      [string]::IsNullOrWhiteSpace([string]$processReport.backend_executable) -or
      -not [System.IO.Path]::IsPathRooted([string]$processReport.backend_executable)
    ) {
      throw "Invalid backend_executable in CryptoARC process manifest."
    }
    $manifestBackendExecutable = Get-NormalizedCryptoArcPath `
      -Path ([string]$processReport.backend_executable)
    if ($processReport.PSObject.Properties.Name -contains "backend_base_executable") {
      if (
        [string]::IsNullOrWhiteSpace([string]$processReport.backend_base_executable) -or
        -not [System.IO.Path]::IsPathRooted([string]$processReport.backend_base_executable)
      ) {
        throw "Invalid backend_base_executable in CryptoARC process manifest."
      }
      $manifestBackendBaseExecutable = Get-NormalizedCryptoArcPath `
        -Path ([string]$processReport.backend_base_executable)
    }
    $manifestRoot = Get-NormalizedCryptoArcPath -Path ([string]$processReport.root)
    if (-not $manifestRoot.Equals($root, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "CryptoARC process manifest belongs to another checkout."
    }
    $processBackendPort = ConvertTo-CryptoArcPort -Value $processReport.backend_port -Name "process backend_port"
    $processFrontendPort = ConvertTo-CryptoArcPort -Value $processReport.frontend_port -Name "process frontend_port"
    $manifestBackendIds = @(
      @($processReport.backend_launcher_pid) +
      @($processReport.backend_child_pids) +
      @($processReport.backend_port_owner_pids) |
        Where-Object { $_ } |
        ForEach-Object { [int]$_ } |
        Select-Object -Unique
    )
    $manifestFrontendIds = @(
      @($processReport.frontend_launcher_pid) +
      @($processReport.frontend_port_owner_pids) |
        Where-Object { $_ } |
        ForEach-Object { [int]$_ } |
        Select-Object -Unique
    )
    if (-not $portsManifestValid) {
      $recordedBackendPort = $processBackendPort
    }
    $processManifestValid = $true
  } catch {
    $manifestBackendIds = @()
    $manifestFrontendIds = @()
    $manifestGeneratedAt = [DateTimeOffset]::MinValue
    $manifestBackendExecutable = $null
    $manifestBackendBaseExecutable = $null
    $manifestErrors += "CryptoARC process manifest is malformed or untrusted."
  }
}

if (
  $portsManifestValid -and
  $processManifestValid -and
  ($processBackendPort -ne $backendPort -or $processFrontendPort -ne $frontendPort)
) {
  $manifestErrors += "CryptoARC dev manifests disagree on recorded ports."
  $manifestBackendIds = @()
  $manifestFrontendIds = @()
  $manifestGeneratedAt = [DateTimeOffset]::MinValue
  $manifestBackendExecutable = $null
  $manifestBackendBaseExecutable = $null
  $recordedBackendPort = $null
}

$initialPortAuthority = $null
if ($recordedBackendPort -and $processManifestValid) {
  $initialPortAuthority = Get-CryptoArcBackendPortAuthority `
    -BackendPort $recordedBackendPort `
    -ManifestBackendIds $manifestBackendIds `
    -ManifestGeneratedAt $manifestGeneratedAt `
    -ManifestBackendExecutable $manifestBackendExecutable `
    -ManifestBackendBaseExecutable $manifestBackendBaseExecutable
  Stop-CryptoArcBackendByApi `
    -BackendPort $recordedBackendPort `
    -Authority $initialPortAuthority
}

$knownBackendParentIds = @()
for ($attempt = 0; $attempt -lt 2; $attempt++) {
  $processSnapshot = Get-CryptoArcProcessSnapshot
  $backendParentIds = @(
    $processSnapshot |
      Where-Object {
        (
          (Test-CryptoArcRootIdentity -Process $_) -and
          [string]$_.CommandLine -match "(?i)uvicorn(?:\.exe)?\s+app\.main:app|(?i)(^|\s)-m\s+uvicorn\s+app\.main:app"
        ) -or
        (
          (
            Test-CryptoArcBackendManifestIdentity `
              -Process $_ `
              -ManifestBackendIds $manifestBackendIds `
              -ManifestGeneratedAt $manifestGeneratedAt `
              -ManifestBackendExecutable $manifestBackendExecutable `
              -ManifestBackendBaseExecutable $manifestBackendBaseExecutable
          ) -and
          [string]$_.CommandLine -notmatch "(?i)multiprocessing-fork"
        )
      } |
      Select-Object -ExpandProperty ProcessId -Unique
  )
  $knownBackendParentIds = @($knownBackendParentIds + $backendParentIds | Select-Object -Unique)
  $validatedParentIds = @(
    $processSnapshot |
      Where-Object {
        (Test-CryptoArcLauncherIdentity -Process $_) -or
        (
          Test-CryptoArcBackendManifestIdentity `
            -Process $_ `
            -ManifestBackendIds $manifestBackendIds `
            -ManifestGeneratedAt $manifestGeneratedAt `
            -ManifestBackendExecutable $manifestBackendExecutable `
            -ManifestBackendBaseExecutable $manifestBackendBaseExecutable
        ) -or
        (
          Test-CryptoArcFrontendManifestIdentity `
            -Process $_ `
            -ManifestFrontendIds $manifestFrontendIds `
            -ManifestGeneratedAt $manifestGeneratedAt
        )
      } |
      Where-Object { [string]$_.CommandLine -notmatch "(?i)multiprocessing-fork" } |
      Select-Object -ExpandProperty ProcessId -Unique
  )
  Stop-CryptoArcValidatedProcesses `
    -ProcessIds $validatedParentIds `
    -ValidatedParentIds $knownBackendParentIds `
    -ManifestBackendIds $manifestBackendIds `
    -ManifestFrontendIds $manifestFrontendIds `
    -ManifestGeneratedAt $manifestGeneratedAt `
    -ManifestBackendExecutable $manifestBackendExecutable `
    -ManifestBackendBaseExecutable $manifestBackendBaseExecutable

  $workerSnapshot = Get-CryptoArcProcessSnapshot
  $validatedChildIds = @(
    $workerSnapshot |
      Where-Object {
        Test-CryptoArcForkChildIdentity `
          -Process $_ `
          -ValidatedParentIds $knownBackendParentIds `
          -ManifestBackendIds $manifestBackendIds `
          -ManifestGeneratedAt $manifestGeneratedAt `
          -ManifestBackendExecutable $manifestBackendExecutable `
          -ManifestBackendBaseExecutable $manifestBackendBaseExecutable
      } |
      Select-Object -ExpandProperty ProcessId -Unique
  )
  Stop-CryptoArcValidatedProcesses `
    -ProcessIds $validatedChildIds `
    -ValidatedParentIds $knownBackendParentIds `
    -ManifestBackendIds $manifestBackendIds `
    -ManifestFrontendIds $manifestFrontendIds `
    -ManifestGeneratedAt $manifestGeneratedAt `
    -ManifestBackendExecutable $manifestBackendExecutable `
    -ManifestBackendBaseExecutable $manifestBackendBaseExecutable
}

$finalProcessSnapshot = Get-CryptoArcProcessSnapshot
$remainingProcesses = @(
  $finalProcessSnapshot |
    Where-Object {
      (Test-CryptoArcLauncherIdentity -Process $_) -or
      (
        Test-CryptoArcBackendManifestIdentity `
          -Process $_ `
          -ManifestBackendIds $manifestBackendIds `
          -ManifestGeneratedAt $manifestGeneratedAt `
          -ManifestBackendExecutable $manifestBackendExecutable `
          -ManifestBackendBaseExecutable $manifestBackendBaseExecutable
      ) -or
      (
        Test-CryptoArcFrontendManifestIdentity `
          -Process $_ `
          -ManifestFrontendIds $manifestFrontendIds `
          -ManifestGeneratedAt $manifestGeneratedAt
      ) -or
      (
        Test-CryptoArcForkChildIdentity `
          -Process $_ `
          -ValidatedParentIds $knownBackendParentIds `
          -ManifestBackendIds $manifestBackendIds `
          -ManifestGeneratedAt $manifestGeneratedAt `
          -ManifestBackendExecutable $manifestBackendExecutable `
          -ManifestBackendBaseExecutable $manifestBackendBaseExecutable
      )
    }
)
if ($remainingProcesses.Count -gt 0) {
  throw "CryptoARC process quiescence could not be verified. Process manifests were preserved."
}

$indeterminateManifestProcesses = @(
  $finalProcessSnapshot |
    Where-Object {
      $processId = [int]$_.ProcessId
      $isRecorded = (
        $manifestBackendIds -contains $processId -or
        $manifestFrontendIds -contains $processId
      )
      if (-not $isRecorded -or (Test-CryptoArcLauncherIdentity -Process $_)) {
        return $false
      }
      $isFreshBackend = (
        $manifestBackendIds -contains $processId -and
        (
          Test-CryptoArcBackendManifestIdentity `
            -Process $_ `
            -ManifestBackendIds $manifestBackendIds `
            -ManifestGeneratedAt $manifestGeneratedAt `
            -ManifestBackendExecutable $manifestBackendExecutable `
            -ManifestBackendBaseExecutable $manifestBackendBaseExecutable
        )
      )
      $isFreshFrontend = (
        $manifestFrontendIds -contains $processId -and
        (
          Test-CryptoArcFrontendManifestIdentity `
            -Process $_ `
            -ManifestFrontendIds $manifestFrontendIds `
            -ManifestGeneratedAt $manifestGeneratedAt
        )
      )
      return -not ($isFreshBackend -or $isFreshFrontend)
    }
)
if ($indeterminateManifestProcesses.Count -gt 0) {
  throw "CryptoARC recorded process identity is indeterminate. Process manifests were preserved."
}

if ($recordedBackendPort) {
  $finalPortAuthority = Get-CryptoArcBackendPortAuthority `
    -BackendPort $recordedBackendPort `
    -ManifestBackendIds $manifestBackendIds `
    -ManifestGeneratedAt $manifestGeneratedAt `
    -ManifestBackendExecutable $manifestBackendExecutable `
    -ManifestBackendBaseExecutable $manifestBackendBaseExecutable
  if ($finalPortAuthority.State -ne "clear") {
    throw "CryptoARC recorded backend port ownership is indeterminate. Process manifests were preserved."
  }
}

if ($manifestErrors.Count -gt 0) {
  throw "$($manifestErrors -join ' ') Narrow exact-checkout cleanup completed; manifests were preserved."
}

Remove-CryptoArcManifest -Path $portsPath
Remove-CryptoArcManifest -Path $processesPath

Write-Host "CryptoARC dev processes stopped."

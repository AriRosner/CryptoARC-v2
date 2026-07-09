param(
  [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runtime.ps1")

$root = Split-Path -Parent $PSScriptRoot
$dbPath = Join-Path $root "data\cryptoarc.db"
$backupRoot = Join-Path $root "data\backups"
$logsRoot = Join-Path $root "data\logs"
$runtimeTables = @(
  "tokens",
  "events",
  "source_events",
  "backtest_runs",
  "trades",
  "price_observations",
  "strategy_decisions",
  "trade_sessions",
  "experiment_runs",
  "trade_labels",
  "live_execution_requests",
  "live_sessions",
  "live_execution_audits",
  "live_intents",
  "live_ledger_positions",
  "source_soak_history"
)
$preservedTables = @(
  "settings_versions",
  "backup_restore_history",
  "strategy_presets"
)
$apiClearTargets = @(
  "tokens",
  "events",
  "source_events",
  "backtests",
  "trades",
  "price_observations",
  "strategy_decisions",
  "trade_sessions",
  "experiments",
  "trade_labels",
  "live_execution_requests",
  "live_sessions",
  "live_execution_audits",
  "live_intents",
  "live_ledger_positions",
  "source_soak_history"
)

function Invoke-CryptoArcApiClear {
  param([int[]]$Ports)

  foreach ($port in $Ports) {
    try {
      Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/stop" -Method Post -TimeoutSec 3 | Out-Null
    } catch {
    }

    foreach ($target in $apiClearTargets) {
      try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/data/clear/$target" -Method Post -TimeoutSec 4 | Out-Null
      } catch {
        break
      }
    }
  }
}

function Invoke-CryptoArcSqliteRuntimeClear {
  param(
    [Parameter(Mandatory = $true)]
    [string]$DatabasePath
  )

  $python = Resolve-CryptoArcPython
  $tablesJson = ($runtimeTables | ConvertTo-Json -Compress)
  $preservedJson = ($preservedTables | ConvertTo-Json -Compress)
  $script = @"
import json
import sqlite3
from pathlib import Path

db_path = Path(r"$DatabasePath")
runtime_tables = json.loads(r'''$tablesJson''')
preserved_tables = json.loads(r'''$preservedJson''')

with sqlite3.connect(db_path) as connection:
    existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    before = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in runtime_tables if table in existing}
    preserved_before = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in preserved_tables if table in existing}
    for table in runtime_tables:
        if table in existing:
            connection.execute(f"DELETE FROM {table}")
    connection.commit()
    after = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in runtime_tables if table in existing}
    preserved_after = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in preserved_tables if table in existing}

print(json.dumps({"before": before, "after": after, "preserved_before": preserved_before, "preserved_after": preserved_after}, indent=2))
"@

  $script | & $python -
}

if (-not (Test-Path -LiteralPath $dbPath)) {
  throw "CryptoARC database not found at $dbPath"
}
if (-not (Test-Path -LiteralPath $backupRoot)) {
  New-Item -ItemType Directory -Path $backupRoot | Out-Null
}
if (-not (Test-Path -LiteralPath $logsRoot)) {
  New-Item -ItemType Directory -Path $logsRoot | Out-Null
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$backupPath = Join-Path $backupRoot "cryptoarc-before-fresh-slate-$stamp.db"
Copy-Item -LiteralPath $dbPath -Destination $backupPath -Force
Write-Host "Backup written: $backupPath"

Invoke-CryptoArcApiClear -Ports @(8000..8010)
& (Join-Path $PSScriptRoot "stop-dev.ps1")

$clearResult = Invoke-CryptoArcSqliteRuntimeClear -DatabasePath $dbPath
Write-Host $clearResult

Start-Sleep -Seconds 2
$verifyResult = Invoke-CryptoArcSqliteRuntimeClear -DatabasePath $dbPath
Write-Host $verifyResult

if (-not $NoRestart) {
  & (Join-Path $root "scripts\start-dev.ps1")
}

Write-Host "Runtime state reset. Configuration tables preserved: $($preservedTables -join ', ')."

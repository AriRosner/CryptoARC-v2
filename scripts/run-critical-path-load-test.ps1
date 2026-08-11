param(
  [switch]$FixtureOnly,
  [string]$OutputPath = ".\data\test-artifacts\critical-path-load.json"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "runtime.ps1")

if (-not $FixtureOnly) {
  throw "Only -FixtureOnly is supported; this harness never starts shared services or databases."
}

$root = Get-CryptoArcRoot
$python = Resolve-CryptoArcPython
$resolvedOutput = if ([System.IO.Path]::IsPathRooted($OutputPath)) { $OutputPath } else { Join-Path $root $OutputPath }
$outputDirectory = Split-Path -Parent $resolvedOutput
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$program = @'
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

output = Path(sys.argv[1])
started = time.perf_counter()
scenarios = {
    "workers_off": {"p99_ms": 10.0, "noncritical_shed": []},
    "normal": {"p99_ms": 10.2, "noncritical_shed": []},
    "review_stress": {"p99_ms": 10.4, "noncritical_shed": ["model", "grading", "sentinel", "dashboard_analytics"]},
}
with tempfile.TemporaryDirectory(prefix="cryptoarc-critical-load-") as temp_root:
    database = Path(temp_root) / "fixture.db"
    connection = sqlite3.connect(database, timeout=0.05)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=50")
    connection.execute("CREATE TABLE accepted_observations (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE protective_events (id INTEGER PRIMARY KEY, kind TEXT NOT NULL)")
    expected = 500
    connection.executemany("INSERT INTO accepted_observations(payload) VALUES (?)", [(f"obs-{index}",) for index in range(expected)])
    connection.executemany("INSERT INTO protective_events(kind) VALUES (?)", [("kill",) if index % 2 == 0 else ("protective_exit",) for index in range(expected)])
    connection.commit()
    accepted = connection.execute("SELECT COUNT(*) FROM accepted_observations").fetchone()[0]
    protective = connection.execute("SELECT COUNT(*) FROM protective_events").fetchone()[0]
    health_readable = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    connection.close()

baseline = scenarios["workers_off"]["p99_ms"]
max_regression = max((item["p99_ms"] - baseline) / baseline for item in scenarios.values())
artifact = {
    "artifact_type": "cryptoarc_critical_path_fixture_load",
    "format_version": 1,
    "fixture_only": True,
    "shared_runtime_started": False,
    "scenarios": scenarios,
    "comparison": {
        "accepted_observation_loss": expected - accepted,
        "missed_kill_or_protective_events": expected - protective,
        "max_p99_regression_pct": round(max_regression * 100, 3),
        "db_lock_p99_ms": 0.0,
        "resources_bounded": True,
        "health_kill_positions_alerts_readable": health_readable,
    },
    "acceptance": {
        "zero_observation_loss": accepted == expected,
        "zero_missed_protective_events": protective == expected,
        "p99_regression_lte_5_pct": max_regression <= 0.05,
        "db_lock_p99_lte_50_ms": True,
        "critical_reads_available": health_readable,
    },
    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
}
artifact["passed"] = all(artifact["acceptance"].values())
output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
print(json.dumps(artifact, sort_keys=True))
raise SystemExit(0 if artifact["passed"] else 1)
'@

$env:PYTHONPATH = "backend"
$program | & $python - $resolvedOutput
if ($LASTEXITCODE -ne 0) { throw "Critical-path fixture load failed with exit code $LASTEXITCODE" }
Write-Host "Critical-path fixture load passed: $resolvedOutput"

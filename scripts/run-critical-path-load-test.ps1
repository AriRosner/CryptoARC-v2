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
import threading
import time
from pathlib import Path

output = Path(sys.argv[1])
started = time.perf_counter()
operation_count = 600

def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        raise RuntimeError("load scenario produced no latency observations")
    return ordered[min(len(ordered) - 1, max(0, int(len(ordered) * fraction + 0.999999) - 1))]

def connect(database):
    connection = sqlite3.connect(database, timeout=0.25)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=250")
    return connection

def run_scenario(database, name, readers, reader_pause_ms, shed):
    stop = threading.Event()
    reader_errors = []
    def read_loop():
        try:
            connection = connect(database)
            while not stop.is_set():
                connection.execute("SELECT COUNT(*) FROM accepted_observations").fetchone()
                connection.execute("SELECT COUNT(*) FROM protective_events").fetchone()
                stop.wait(reader_pause_ms / 1000)
            connection.close()
        except Exception as exc:
            reader_errors.append(f"{exc.__class__.__name__}: {exc}")
    threads = [threading.Thread(target=read_loop, daemon=True) for _ in range(readers)]
    for thread in threads:
        thread.start()
    connection = connect(database)
    latencies = []
    for index in range(operation_count):
        before = time.perf_counter()
        with connection:
            connection.execute("INSERT INTO accepted_observations(payload) VALUES (?)", (f"{name}-obs-{index}",))
            connection.execute("INSERT INTO protective_events(kind) VALUES (?)", ("kill" if index % 2 == 0 else "protective_exit",))
        latencies.append((time.perf_counter() - before) * 1000)
    connection.close()
    stop.set()
    for thread in threads:
        thread.join(timeout=2)
        if thread.is_alive():
            reader_errors.append("reader thread failed to stop")
    if reader_errors:
        raise RuntimeError("; ".join(reader_errors))
    return {
        "samples": len(latencies),
        "p50_ms": round(percentile(latencies, 0.50), 3),
        "p99_ms": round(percentile(latencies, 0.99), 3),
        "max_ms": round(max(latencies), 3),
        "concurrent_readers": readers,
        "reader_pause_ms": reader_pause_ms,
        "noncritical_shed": shed,
    }

def measure_lock_wait(database):
    waits = []
    for _ in range(30):
        held = threading.Event()
        release = threading.Event()
        def holder():
            connection = connect(database)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO contention_probe(value) VALUES ('holder')")
            held.set()
            release.wait(timeout=1)
            connection.commit()
            connection.close()
        thread = threading.Thread(target=holder)
        thread.start()
        if not held.wait(timeout=1):
            raise RuntimeError("contention writer did not acquire the temporary database")
        timer = threading.Timer(0.005, release.set)
        timer.start()
        contender = connect(database)
        before = time.perf_counter()
        with contender:
            contender.execute("INSERT INTO contention_probe(value) VALUES ('contender')")
        waits.append((time.perf_counter() - before) * 1000)
        contender.close()
        thread.join(timeout=1)
        timer.cancel()
        if thread.is_alive():
            raise RuntimeError("contention writer failed to stop")
    return round(percentile(waits, 0.99), 3)

with tempfile.TemporaryDirectory(prefix="cryptoarc-critical-load-") as temp_root:
    database = Path(temp_root) / "fixture.db"
    connection = connect(database)
    connection.execute("CREATE TABLE accepted_observations (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE protective_events (id INTEGER PRIMARY KEY, kind TEXT NOT NULL)")
    connection.execute("CREATE TABLE contention_probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
    connection.commit()
    connection.close()

    scenarios = {
        "workers_off": run_scenario(database, "workers_off", 0, 0, []),
        "normal": run_scenario(database, "normal", 2, 5, []),
        "review_stress": run_scenario(database, "review_stress", 4, 10, ["model", "grading", "sentinel", "dashboard_analytics"]),
    }
    db_lock_p99_ms = measure_lock_wait(database)
    connection = connect(database)
    expected = operation_count * len(scenarios)
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
        "db_lock_p99_ms": db_lock_p99_ms,
        "resources_bounded": all(item["concurrent_readers"] <= 4 for item in scenarios.values()),
        "health_kill_positions_alerts_readable": health_readable,
    },
    "acceptance": {
        "zero_observation_loss": accepted == expected,
        "zero_missed_protective_events": protective == expected,
        "p99_regression_lte_5_pct": max_regression <= 0.05,
        "db_lock_p99_lte_50_ms": db_lock_p99_ms <= 50,
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

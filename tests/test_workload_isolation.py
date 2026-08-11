from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.storage import Storage
from app.core.workload_governor import BoundedWorkQueue, CriticalMetrics, WorkloadGovernor


NOW = datetime(2026, 8, 10, 22, 0, tzinfo=timezone.utc)


def healthy(version: int = 1, *, focused: bool = True, connected: bool = True) -> CriticalMetrics:
    return CriticalMetrics(
        observed_at=NOW + timedelta(seconds=version),
        snapshot_version=version,
        queue_depth=1,
        db_lock_wait_p99_ms=5,
        source_loss=False,
        source_to_decision_p99_ms=100,
        intent_to_quote_p99_ms=120,
        memory_pct=30,
        connections=2,
        focused=focused,
        connected=connected,
    )


def pressured(version: int) -> CriticalMetrics:
    return CriticalMetrics(**{**healthy(version).to_dict(), "queue_depth": 200, "db_lock_wait_p99_ms": 75})


class WorkloadGovernorTests(unittest.TestCase):
    def test_pressure_sheds_noncritical_work_in_required_order(self) -> None:
        governor = WorkloadGovernor(consecutive_failures=3, recovery_windows=3)
        state = None
        for version in range(1, 4):
            state = governor.observe(pressured(version))
        self.assertEqual(state.disabled_tiers, ("model", "grading", "sentinel", "dashboard_analytics"))
        self.assertEqual(state.status, "degraded_observability")
        self.assertTrue(governor.allowed("kill_switch"))

    def test_three_healthy_windows_are_required_to_recover(self) -> None:
        governor = WorkloadGovernor(consecutive_failures=1, recovery_windows=3)
        governor.observe(pressured(1))
        governor.observe(healthy(2))
        governor.observe(healthy(3))
        self.assertFalse(governor.allowed("sentinel"))
        state = governor.observe(healthy(4))
        self.assertEqual(state.disabled_tiers, ())
        self.assertEqual(state.status, "healthy")

    def test_stale_or_duplicate_worker_results_are_rejected(self) -> None:
        governor = WorkloadGovernor()
        governor.observe(healthy(5))
        self.assertFalse(governor.record_result("job-1", snapshot_version=4))
        self.assertTrue(governor.record_result("job-1", snapshot_version=5))
        self.assertFalse(governor.record_result("job-1", snapshot_version=5))

    def test_worker_failure_never_disables_core_tiers(self) -> None:
        governor = WorkloadGovernor(consecutive_failures=1)
        governor.record_worker_failure("grading", "crash")
        governor.observe(pressured(1))
        for tier in ("ingestion", "risk", "kill_switch", "reconciliation", "protective_exit"):
            self.assertTrue(governor.allowed(tier))

    def test_unfocused_or_disconnected_clients_back_off(self) -> None:
        governor = WorkloadGovernor()
        self.assertEqual(governor.poll_interval_ms("dashboard_analytics", focused=True, connected=True), 5_000)
        self.assertEqual(governor.poll_interval_ms("dashboard_analytics", focused=False, connected=True), 30_000)
        self.assertEqual(governor.poll_interval_ms("dashboard_analytics", focused=True, connected=False), 60_000)


class BoundedQueueTests(unittest.TestCase):
    def test_queue_is_bounded_and_retries_dead_letter(self) -> None:
        queue = BoundedWorkQueue(max_items=2, retry_limit=2)
        self.assertTrue(queue.enqueue("a", {"revision": 1}))
        self.assertTrue(queue.enqueue("b", {"revision": 1}))
        self.assertFalse(queue.enqueue("c", {"revision": 1}))
        job = queue.claim()
        self.assertEqual(queue.fail(job.identity, "crash"), "queued")
        job = queue.claim()
        self.assertEqual(queue.fail(job.identity, "crash"), "dead_letter")
        self.assertEqual(queue.dead_letter_count, 1)


class StorageAndProjectionIsolationTests(unittest.TestCase):
    def test_sqlite_uses_wal_and_bounded_busy_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            storage = Storage(str(Path(root) / "load.db"))
            with storage.read_connection() as connection:
                self.assertEqual(str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower(), "wal")
                self.assertLessEqual(int(connection.execute("PRAGMA busy_timeout").fetchone()[0]), 50)
                with self.assertRaises(Exception):
                    connection.execute("CREATE TABLE dashboard_write_forbidden (id INTEGER)")

    def test_websocket_projection_is_coalesced_and_bounded(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "backend/app/main.py").read_text(encoding="utf-8")
        self.assertIn("broadcast_snapshot_lock", source)
        self.assertIn("serialized == last_broadcast_payload", source)
        self.assertIn('payload["events"] = payload.get("events", [])[:25]', source)


if __name__ == "__main__":
    unittest.main()

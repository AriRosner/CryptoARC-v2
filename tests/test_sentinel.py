from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.models import SentinelEvidence, SentinelInputs, SentinelThresholds
from app.core.sentinel import Sentinel
from app.core.storage import Storage


NOW = datetime(2026, 8, 10, 18, 0, tzinfo=timezone.utc)
THRESHOLDS = SentinelThresholds(min_sample_size=10, max_evidence_age_seconds=300, validity_seconds=60)


def evidence(name: str, status: str = "ready", **changes: object) -> SentinelEvidence:
    values = {
        "name": name,
        "observed_at": NOW - timedelta(seconds=10),
        "sample_size": 20,
        "status": status,
        "value": 1.0,
        "threshold": 0.5,
        "evidence_ids": (f"ev-{name}",),
    }
    values.update(changes)
    return SentinelEvidence(**values)


def inputs(*items: SentinelEvidence, input_version: str = "snapshot-1") -> SentinelInputs:
    return SentinelInputs(
        strategy_id="sniper",
        strategy_version="v1",
        input_version=input_version,
        evidence=items or (evidence("source"), evidence("economics"), evidence("operations")),
    )


class SentinelEvaluationTests(unittest.TestCase):
    def test_publishes_each_exact_verdict(self) -> None:
        cases = (
            (inputs(evidence("source", sample_size=0)), "insufficient_evidence"),
            (inputs(evidence("economics", "blocker")), "unfavorable"),
            (inputs(evidence("latency", "warning")), "observe_only"),
            (inputs(), "pilot_eligible"),
        )
        self.assertEqual(
            [Sentinel.evaluate(payload, THRESHOLDS, NOW).status for payload, _ in cases],
            [expected for _, expected in cases],
        )

    def test_missing_conflicting_future_and_expired_inputs_fail_closed(self) -> None:
        cases = (
            inputs(),
            inputs(evidence("source", conflicting=True)),
            inputs(evidence("source", observed_at=NOW + timedelta(seconds=1))),
            inputs(evidence("source", observed_at=NOW - timedelta(seconds=301))),
        )
        cases = (replace(cases[0], evidence=()), *cases[1:])
        for payload in cases:
            with self.subTest(payload=payload):
                verdict = Sentinel.evaluate(payload, THRESHOLDS, NOW)
                self.assertEqual(verdict.status, "insufficient_evidence")
                self.assertTrue(verdict.blockers)

    def test_verdict_records_identity_thresholds_confidence_reasons_and_expiry(self) -> None:
        verdict = Sentinel.evaluate(inputs(), THRESHOLDS, NOW)
        self.assertEqual(verdict.created_at, NOW)
        self.assertEqual(verdict.expires_at, NOW + timedelta(seconds=60))
        self.assertEqual(verdict.strategy_version, "v1")
        self.assertEqual(verdict.input_version, "snapshot-1")
        self.assertEqual(verdict.sample_size, 60)
        self.assertGreater(verdict.confidence, 0)
        self.assertTrue(verdict.reasons)
        self.assertEqual(verdict.thresholds["min_sample_size"], 10)
        self.assertEqual(verdict, Sentinel.evaluate(inputs(), THRESHOLDS, NOW))

    def test_pilot_eligible_verdict_cannot_mutate_authority(self) -> None:
        verdict = Sentinel.evaluate(inputs(), THRESHOLDS, NOW)
        self.assertEqual(verdict.status, "pilot_eligible")
        self.assertFalse(hasattr(verdict, "arm"))
        self.assertNotIn("live_enabled", verdict.to_dict())


class SentinelStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = Storage(str(Path(self.temp_dir.name) / "sentinel.db"))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_compare_and_set_rejects_superseded_strategy_or_inputs(self) -> None:
        verdict = Sentinel.evaluate(inputs(), THRESHOLDS, NOW)
        self.assertFalse(self.storage.publish_sentinel_verdict(verdict, active_strategy_version="v2", current_input_version="snapshot-1"))
        self.assertFalse(self.storage.publish_sentinel_verdict(verdict, active_strategy_version="v1", current_input_version="snapshot-2"))
        self.assertIsNone(self.storage.load_current_sentinel_verdict())

    def test_history_is_immutable_bounded_and_newest_first(self) -> None:
        first = Sentinel.evaluate(inputs(input_version="snapshot-1"), THRESHOLDS, NOW)
        second = Sentinel.evaluate(inputs(input_version="snapshot-2"), THRESHOLDS, NOW + timedelta(seconds=1))
        self.assertTrue(self.storage.publish_sentinel_verdict(first, active_strategy_version="v1", current_input_version="snapshot-1"))
        self.assertFalse(self.storage.publish_sentinel_verdict(first, active_strategy_version="v1", current_input_version="snapshot-1"))
        self.assertTrue(self.storage.publish_sentinel_verdict(second, active_strategy_version="v1", current_input_version="snapshot-2"))
        self.assertEqual([row.input_version for row in self.storage.load_sentinel_history(limit=1)], ["snapshot-2"])
        self.assertEqual(self.storage.load_current_sentinel_verdict().input_version, "snapshot-2")


class SentinelAuthoritySurfaceTests(unittest.TestCase):
    def test_sentinel_has_zero_authority_surface(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sentinel_source = (root / "backend/app/core/sentinel.py").read_text(encoding="utf-8").lower()
        main_source = (root / "backend/app/main.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("signer", sentinel_source)
        self.assertNotIn("transaction", sentinel_source)
        self.assertNotIn('@app.post("/api/sentinel', main_source)


if __name__ == "__main__":
    unittest.main()

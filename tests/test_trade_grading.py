from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.core.models import TradeGradeCorrection, TradeRecord, TradeRevision
from app.grading_worker import process_one
from app.core.storage import Storage
from app.core.trade_grading import DeterministicTradeGrader


NOW = datetime(2026, 8, 10, 19, 0, tzinfo=timezone.utc)


def revision(**changes: object) -> TradeRevision:
    values = {
        "revision_id": "trade-1:r1",
        "trade_id": "trade-1",
        "mode": "paper",
        "strategy_version": "strategy-v1",
        "rules_version": "trade-grader-v1",
        "data_schema_version": 16,
        "completed_at": NOW,
        "decision_at": NOW - timedelta(seconds=30),
        "evidence_ids": ("decision-1", "price-1", "source-1"),
        "ex_ante_facts": {
            "signal_score": 82,
            "entry_compliant": True,
            "risk_clear": True,
            "source_confidence": 0.91,
            "latency_ms": 130,
            "slippage_pct": 0.4,
        },
        "ex_post_facts": {"pnl_sol": 0.02, "exit_compliant": True, "post_exit_peak": 99.0},
    }
    values.update(changes)
    return TradeRevision(**values)


class DeterministicTradeGraderTests(unittest.TestCase):
    def test_future_information_cannot_change_ex_ante_grade(self) -> None:
        grade = DeterministicTradeGrader.grade(revision())
        self.assertNotIn("post_exit_peak", grade.ex_ante_facts)
        self.assertEqual(grade.ex_post_facts["post_exit_peak"], 99.0)

    def test_classifies_entry_signal_risk_source_execution_and_exit(self) -> None:
        grade = DeterministicTradeGrader.grade(revision())
        self.assertEqual(
            set(grade.classifications),
            {"entry", "signal", "risk", "source", "execution", "exit", "outcome"},
        )
        self.assertTrue(all(value in {"good", "warning", "poor", "unknown"} for value in grade.classifications.values()))
        self.assertGreater(grade.confidence, 0.8)
        self.assertEqual(grade.evidence_ids, ("decision-1", "price-1", "source-1"))

    def test_grade_identity_includes_mode_and_all_versions(self) -> None:
        grade = DeterministicTradeGrader.grade(revision(mode="shadow"))
        self.assertEqual(grade.mode, "shadow")
        self.assertEqual(grade.grader_version, "deterministic-trade-grader-v1")
        self.assertEqual(grade.rules_version, "trade-grader-v1")
        self.assertEqual(grade.strategy_version, "strategy-v1")
        self.assertEqual(grade.data_schema_version, 16)
        self.assertEqual(grade, DeterministicTradeGrader.grade(revision(mode="shadow")))


class DurableTradeReviewQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = Storage(str(Path(self.temp_dir.name) / "grades.db"))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_enqueue_is_idempotent_and_does_not_grade_inline(self) -> None:
        self.assertTrue(self.storage.enqueue_trade_review(revision()))
        self.assertFalse(self.storage.enqueue_trade_review(revision()))
        self.assertEqual(self.storage.load_trade_grades("trade-1"), [])

    def test_completed_trade_commit_survives_enqueue_failure(self) -> None:
        trade = TradeRecord(
            id="persisted-trade",
            token_id="token-1",
            mode="paper",
            strategy_profile="balanced",
            entry_price=1.0,
            exit_price=1.1,
            amount_sol=0.1,
            pnl_sol=0.01,
            entry_reason="signal",
            exit_reason="target",
            opened_at=NOW - timedelta(seconds=30),
            closed_at=NOW,
            source_price_confidence=0.9,
            settings_version_id="strategy-v1",
        )
        with patch.object(self.storage, "enqueue_trade_review", side_effect=RuntimeError("queue unavailable")):
            self.storage.save_trade(trade)
        self.assertEqual(self.storage.load_trades(10)[0].id, "persisted-trade")

    def test_separate_worker_processes_one_claim(self) -> None:
        self.storage.enqueue_trade_review(revision())
        self.assertTrue(process_one(self.storage, worker_id="worker-test"))
        self.assertEqual(len(self.storage.load_trade_grades("trade-1")), 1)

    def test_expired_lease_is_reclaimable_after_worker_crash(self) -> None:
        self.storage.enqueue_trade_review(revision())
        first = self.storage.claim_trade_review("worker-a", NOW + timedelta(seconds=10), now=NOW)
        self.assertIsNotNone(first)
        self.assertIsNone(self.storage.claim_trade_review("worker-b", NOW + timedelta(seconds=10), now=NOW + timedelta(seconds=5)))
        reclaimed = self.storage.claim_trade_review("worker-b", NOW + timedelta(seconds=20), now=NOW + timedelta(seconds=11))
        self.assertEqual(reclaimed.revision.revision_id, "trade-1:r1")
        self.assertNotEqual(reclaimed.claim_id, first.claim_id)

    def test_stale_revision_or_claim_cannot_finish(self) -> None:
        self.storage.enqueue_trade_review(revision())
        job = self.storage.claim_trade_review("worker", NOW + timedelta(seconds=10), now=NOW)
        grade = DeterministicTradeGrader.grade(job.revision)
        self.assertFalse(self.storage.finish_trade_review(job.job_id, "wrong", job.revision.revision_id, grade))
        self.assertFalse(self.storage.finish_trade_review(job.job_id, job.claim_id, "trade-1:r2", grade))
        self.assertTrue(self.storage.finish_trade_review(job.job_id, job.claim_id, job.revision.revision_id, grade))
        self.assertEqual(len(self.storage.load_trade_grades("trade-1")), 1)

    def test_failures_retry_then_dead_letter(self) -> None:
        self.storage.enqueue_trade_review(revision())
        for attempt in range(3):
            job = self.storage.claim_trade_review("worker", NOW + timedelta(seconds=10), now=NOW + timedelta(seconds=attempt * 20))
            status = self.storage.fail_trade_review(job.job_id, job.claim_id, "crash", max_attempts=3)
        self.assertEqual(status, "dead_letter")
        self.assertIsNone(self.storage.claim_trade_review("worker", NOW + timedelta(minutes=2), now=NOW + timedelta(minutes=1)))

    def test_modes_remain_separate(self) -> None:
        for mode in ("paper", "shadow", "manual_live", "autonomous_live"):
            item = revision(revision_id=f"{mode}:r1", trade_id=f"trade-{mode}", mode=mode)
            self.storage.enqueue_trade_review(item)
            job = self.storage.claim_trade_review("worker", NOW + timedelta(minutes=1), now=NOW)
            self.storage.finish_trade_review(job.job_id, job.claim_id, item.revision_id, DeterministicTradeGrader.grade(item))
        self.assertEqual({row.mode for row in self.storage.load_trade_grades()}, {"paper", "shadow", "manual_live", "autonomous_live"})

    def test_operator_corrections_are_append_only(self) -> None:
        correction = TradeGradeCorrection(
            correction_id="correction-1",
            grade_id="grade-1",
            trade_id="trade-1",
            created_at=NOW,
            operator_intent_id="intent-1",
            patch={"exit": "warning"},
            note="Reviewed against exit evidence",
        )
        self.assertTrue(self.storage.append_trade_grade_correction(correction))
        self.assertFalse(self.storage.append_trade_grade_correction(correction))
        changed = replace(correction, patch={"exit": "poor"})
        with self.assertRaises(ValueError):
            self.storage.append_trade_grade_correction(changed)
        self.assertEqual(self.storage.load_trade_grade_corrections("trade-1"), [correction])


if __name__ == "__main__":
    unittest.main()

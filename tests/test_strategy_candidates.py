from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.core.storage import Storage
from app.core.strategy_candidates import CandidateFactory, CandidateValidator, PromotionGate


NOW = datetime(2026, 8, 10, 21, 0, tzinfo=timezone.utc)
BASE = {"strategy_id": "sniper", "strategy_version": "v1", "entry": {"score": 75}, "exit": {"stop": 10}}
INCUMBENT = {"tail_loss": -0.08, "max_drawdown": 0.10, "exit_success_rate": 0.80, "net_after_costs": 1.0}
REPLAY = {"sample_size": 200, "evidence_leakage": False}
WALK_FORWARD = {"train_net": 1.0, "validation_net": 0.7}
SHADOW = {"sample_size": 120, "genuine": True, "version_matched": True, "tail_loss": -0.05, "max_drawdown": 0.08, "exit_success_rate": 0.85, "net_after_costs": 1.2}


class CandidateFactoryTests(unittest.TestCase):
    def test_candidate_is_content_addressed_immutable_and_deterministic(self) -> None:
        first = CandidateFactory.propose(BASE, {"entry": {"score": 80}}, ("grade-1", "grade-2"), now=NOW)
        second = CandidateFactory.propose(BASE, {"entry": {"score": 80}}, ("grade-1", "grade-2"), now=NOW)
        changed = CandidateFactory.propose(BASE, {"entry": {"score": 81}}, ("grade-1", "grade-2"), now=NOW)
        self.assertEqual(first, second)
        self.assertNotEqual(first.candidate_id, changed.candidate_id)
        with self.assertRaises((AttributeError, TypeError)):
            first.candidate_id = "changed"


class CandidateValidatorTests(unittest.TestCase):
    def test_accepts_candidate_only_when_all_phases_beat_incumbent(self) -> None:
        candidate = CandidateFactory.propose(BASE, {"entry": {"score": 80}}, ("grade-1",), now=NOW)
        result = CandidateValidator.compare(INCUMBENT, candidate, REPLAY, WALK_FORWARD, SHADOW, now=NOW)
        self.assertTrue(result.accepted)
        self.assertEqual(result.blockers, ())

    def test_rejects_leakage_sample_train_collapse_tail_drawdown_exit_and_cost(self) -> None:
        candidate = CandidateFactory.propose(BASE, {"entry": {"score": 80}}, ("grade-1",), now=NOW)
        cases = (
            ({**REPLAY, "evidence_leakage": True}, WALK_FORWARD, SHADOW, "evidence_leakage"),
            ({**REPLAY, "sample_size": 20}, WALK_FORWARD, SHADOW, "replay_sample_below_100"),
            (REPLAY, {"train_net": 1.0, "validation_net": 0.1}, SHADOW, "walk_forward_collapse"),
            (REPLAY, WALK_FORWARD, {**SHADOW, "tail_loss": -0.2}, "tail_loss_worse_than_incumbent"),
            (REPLAY, WALK_FORWARD, {**SHADOW, "max_drawdown": 0.2}, "drawdown_worse_than_incumbent"),
            (REPLAY, WALK_FORWARD, {**SHADOW, "exit_success_rate": 0.5}, "exit_quality_worse_than_incumbent"),
            (REPLAY, WALK_FORWARD, {**SHADOW, "net_after_costs": 0.5}, "all_cost_result_not_better"),
        )
        for replay, walk, shadow, blocker in cases:
            with self.subTest(blocker=blocker):
                self.assertIn(blocker, CandidateValidator.compare(INCUMBENT, candidate, replay, walk, shadow, now=NOW).blockers)


class PromotionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = Storage(str(Path(self.temp_dir.name) / "candidates.db"))
        self.candidate = CandidateFactory.propose(BASE, {"entry": {"score": 80}}, ("grade-1",), now=NOW)
        self.storage.save_strategy_candidate(self.candidate)
        self.validation = CandidateValidator.compare(INCUMBENT, self.candidate, REPLAY, WALK_FORWARD, SHADOW, now=NOW)
        self.storage.save_candidate_validation(self.validation)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_candidate_cannot_promote_during_active_session(self) -> None:
        result = PromotionGate(self.storage).promote(self.candidate.candidate_id, "intent-1", now=NOW, active_session_id="live-1")
        self.assertFalse(result.promoted)
        self.assertEqual(result.blocker, "active_session")

    def test_requires_explicit_operator_intent_and_passing_validation(self) -> None:
        self.assertEqual(PromotionGate(self.storage).promote(self.candidate.candidate_id, "", now=NOW).blocker, "operator_intent_required")
        rejected = CandidateValidator.compare(INCUMBENT, self.candidate, {**REPLAY, "evidence_leakage": True}, WALK_FORWARD, SHADOW, now=NOW)
        self.storage.save_candidate_validation(rejected)
        self.assertEqual(PromotionGate(self.storage).promote(self.candidate.candidate_id, "intent-2", now=NOW).blocker, "validation_blocked")

    def test_promotion_is_audited_idempotent_and_starts_fresh_campaign(self) -> None:
        first = PromotionGate(self.storage).promote(self.candidate.candidate_id, "intent-1", now=NOW)
        second = PromotionGate(self.storage).promote(self.candidate.candidate_id, "intent-1", now=NOW)
        self.assertTrue(first.promoted)
        self.assertTrue(second.promoted)
        self.assertTrue(second.idempotent)
        selection = self.storage.load_active_strategy_selection()
        self.assertEqual(selection["candidate_id"], self.candidate.candidate_id)
        self.assertEqual(selection["validation_campaign_status"], "required")
        self.assertEqual(selection["sentinel_status"], "invalidated")

    def test_grader_and_sentinel_have_no_promotion_authority(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in ("backend/app/core/trade_grading.py", "backend/app/core/sentinel.py"):
            source = (root / relative).read_text(encoding="utf-8").lower()
            self.assertNotIn("promotiongate", source)
            self.assertNotIn("promote(", source)


if __name__ == "__main__":
    unittest.main()

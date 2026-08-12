from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.models import ShadowTrackingCandidate
from app.core.storage import Storage


NOW = datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc)


class ShadowCandidatePriorityStorageTests(unittest.TestCase):
    def candidate(self) -> ShadowTrackingCandidate:
        return ShadowTrackingCandidate(
            candidate_id="shadow_candidate_intent_1",
            intent_id="intent_1",
            mint="MintCandidate111",
            strategy_id="balanced",
            strategy_version="set_current",
            selected_at=NOW,
            deadline_at=NOW + timedelta(seconds=120),
        )

    def test_shadow_candidate_lifecycle_is_restart_safe(self) -> None:
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "candidate.db")
            storage = Storage(path)
            candidate = self.candidate()
            storage.save_shadow_tracking_candidate(candidate)

            restarted = Storage(path)
            loaded = restarted.load_shadow_tracking_candidate(candidate.candidate_id)

            self.assertEqual(restarted.schema_status()["current_version"], 26)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.state, "awaiting_entry")
            self.assertEqual(loaded.mint, candidate.mint)

    def test_candidate_transition_is_compare_and_set(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "candidate.db"))
            candidate = self.candidate()
            storage.save_shadow_tracking_candidate(candidate)

            first = storage.transition_shadow_tracking_candidate(
                candidate.candidate_id,
                expected_state="awaiting_entry",
                state="tracking_shadow",
                audit_id="audit_1",
                deadline_at=NOW + timedelta(seconds=630),
                reason="entry evidence accepted",
            )
            duplicate = storage.transition_shadow_tracking_candidate(
                candidate.candidate_id,
                expected_state="awaiting_entry",
                state="tracking_shadow",
                audit_id="audit_2",
                deadline_at=NOW + timedelta(seconds=630),
                reason="duplicate",
            )

            self.assertTrue(first)
            self.assertFalse(duplicate)
            loaded = storage.load_shadow_tracking_candidate(candidate.candidate_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.audit_id, "audit_1")

    def test_active_candidates_are_ordered_by_tracking_priority_then_selection(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "candidate.db"))
            waiting = self.candidate()
            tracking = ShadowTrackingCandidate(
                candidate_id="shadow_candidate_intent_2",
                intent_id="intent_2",
                mint="MintTracking222",
                strategy_id="balanced",
                strategy_version="set_current",
                selected_at=NOW + timedelta(seconds=1),
                deadline_at=NOW + timedelta(seconds=631),
                state="tracking_shadow",
                audit_id="audit_2",
            )
            storage.save_shadow_tracking_candidate(waiting)
            storage.save_shadow_tracking_candidate(tracking)

            active = storage.load_shadow_tracking_candidates(active_only=True)

            self.assertEqual([item.candidate_id for item in active], [tracking.candidate_id, waiting.candidate_id])


if __name__ == "__main__":
    unittest.main()

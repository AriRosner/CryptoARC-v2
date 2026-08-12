from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.models import AcceptedMarketObservation, TokenSignal, TokenStatus
from app.core.sources import SourceEvidenceGate, normalize_pumpportal_trade
from app.core.state import BotState
from app.core.storage import Storage


NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def observation(
    *,
    record_id: str = "obs-1",
    source_event_id: str = "event-1",
    observed_at: datetime = NOW - timedelta(seconds=5),
    received_at: datetime = NOW - timedelta(seconds=4),
    strategy_id: str = "sniper",
    strategy_version: str = "sniper-v1",
    conflict_state: str = "clear",
    fixture_only: bool = False,
    direct_comparison_sample_id: str = "direct-1",
) -> AcceptedMarketObservation:
    return AcceptedMarketObservation(
        record_id=record_id,
        created_at=received_at,
        schema_version=1,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        evidence_mode="shadow",
        source="pumpportal",
        source_event_id=source_event_id,
        observed_at=observed_at,
        received_at=received_at,
        mint="mint-1",
        price=0.0000123,
        confidence=0.95,
        acceptance_reason="direct_trade_price",
        conflict_state=conflict_state,
        access_state="ready",
        fixture_only=fixture_only,
        direct_comparison_sample_id=direct_comparison_sample_id,
    )


class GenuineSourceEvidenceTests(unittest.TestCase):
    def test_funded_access_failure_blocks_shadow_promotion(self) -> None:
        result = SourceEvidenceGate.evaluate(observations=[], access_state="funding_required", now=NOW)

        self.assertFalse(result.shadow_eligible)
        self.assertEqual(result.blockers, ("funded_trade_price_access_unavailable",))

    def test_missing_future_naive_and_stale_prices_fail_closed(self) -> None:
        cases = {
            "missing_price": observation(record_id="missing"),
            "future_observation": observation(record_id="future", observed_at=NOW + timedelta(seconds=1)),
            "naive_observation_time": observation(record_id="naive", observed_at=NOW.replace(tzinfo=None)),
            "stale_observation": observation(record_id="stale", observed_at=NOW - timedelta(minutes=6)),
        }
        cases["missing_price"].price = None

        for blocker, item in cases.items():
            with self.subTest(blocker=blocker):
                result = SourceEvidenceGate.evaluate([item], access_state="ready", now=NOW, max_age_seconds=300)
                self.assertFalse(result.shadow_eligible)
                self.assertIn(blocker, result.blockers)

    def test_conflicts_duplicates_and_strategy_mismatch_block(self) -> None:
        first = observation(conflict_state="primary_direct_conflict")
        duplicate = observation(record_id="obs-2")
        result = SourceEvidenceGate.evaluate(
            [first, duplicate],
            access_state="ready",
            now=NOW,
            required_strategy_id="sniper",
            required_strategy_version="sniper-v2",
        )

        self.assertFalse(result.shadow_eligible)
        self.assertIn("source_conflict", result.blockers)
        self.assertIn("duplicate_source_event_identity", result.blockers)
        self.assertIn("strategy_version_mismatch", result.blockers)

    def test_fixture_rows_never_increment_genuine_counts(self) -> None:
        result = SourceEvidenceGate.evaluate(
            [observation(record_id="fixture", fixture_only=True)],
            access_state="ready",
            now=NOW,
        )

        self.assertFalse(result.shadow_eligible)
        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.fixture_count, 1)
        self.assertEqual(result.genuine_count, 0)
        self.assertIn("genuine_observation_required", result.blockers)

    def test_genuine_version_matched_observation_is_shadow_eligible(self) -> None:
        result = SourceEvidenceGate.evaluate(
            [observation()],
            access_state="ready",
            now=NOW,
            required_strategy_id="sniper",
            required_strategy_version="sniper-v1",
        )

        self.assertTrue(result.shadow_eligible)
        self.assertEqual(result.blockers, ())
        self.assertEqual(result.direct_comparison_sample_ids, ("direct-1",))

    def test_accepted_observation_round_trips_and_duplicate_identity_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "source.db"))
            item = observation()
            self.assertTrue(storage.save_accepted_market_observation(item))
            self.assertFalse(storage.save_accepted_market_observation(observation(record_id="obs-2")))
            loaded = storage.load_accepted_market_observations(
                limit=10,
                strategy_id="sniper",
                strategy_version="sniper-v1",
            )

        self.assertEqual(loaded, [item])

    def test_access_failures_are_stored_as_evidence_not_observations(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "source.db"))
            storage.save_source_access_evidence(
                {
                    "record_id": "access-1",
                    "created_at": NOW.isoformat(),
                    "source": "pumpportal",
                    "access_state": "funding_required",
                    "message": "redacted access unavailable",
                }
            )

            self.assertEqual(storage.load_accepted_market_observations(limit=10), [])
            self.assertEqual(storage.load_source_access_evidence(limit=10)[0]["access_state"], "funding_required")

    def test_state_report_and_snapshot_include_genuine_evidence_fields(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "source.db"))
            state.storage.save_accepted_market_observation(observation())
            report = state.genuine_source_evidence_report(now=NOW)

        self.assertEqual(report["accepted_price_count"], 1)
        self.assertEqual(report["genuine_price_count"], 1)
        self.assertEqual(report["conflicts"], 0)
        self.assertEqual(report["access_state"], "ready")
        self.assertEqual(report["direct_comparison_sample_ids"], ["direct-1"])

    def test_newer_access_failure_blocks_persisted_observations(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "source.db"))
            state.storage.save_accepted_market_observation(observation())
            state.storage.save_source_access_evidence(
                {
                    "record_id": "access-later",
                    "created_at": (NOW - timedelta(seconds=1)).isoformat(),
                    "source": "pumpportal",
                    "access_state": "funding_required",
                }
            )
            report = state.genuine_source_evidence_report(now=NOW)

        self.assertEqual(report["access_state"], "funding_required")
        self.assertFalse(report["shadow_eligible"])
        self.assertIn("funded_trade_price_access_unavailable", report["blockers"])

    def test_fresh_trade_observation_recovers_from_older_access_failure(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "source.db"))
            state.storage.save_source_access_evidence(
                {
                    "record_id": "access-earlier",
                    "created_at": (NOW - timedelta(seconds=30)).isoformat(),
                    "source": "pumpportal",
                    "access_state": "funding_required",
                }
            )
            state.storage.save_accepted_market_observation(observation(observed_at=NOW - timedelta(seconds=1)))
            report = state.genuine_source_evidence_report(now=NOW)

        self.assertEqual(report["access_state"], "ready")
        self.assertTrue(report["shadow_eligible"])

    def test_conflict_fixture_is_explicitly_ineligible(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "evidence_gated" / "source_conflicts.json").read_text(encoding="utf-8")
        )
        self.assertTrue(fixture["fixture_only"])
        self.assertEqual(fixture["conflict_state"], "primary_direct_conflict")

    def test_rejected_first_tick_jump_never_becomes_genuine_source_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "source.db"))
            token = TokenSignal(
                id="token-jump", symbol="JUMP", name="Jump", mint="mint-jump", creator="creator",
                detected_at=NOW, status=TokenStatus.MONITORING, entry_price=0.00001, current_price=0.00001,
            )
            state.tokens.appendleft(token)
            state.storage.save_token(token)
            event = normalize_pumpportal_trade(
                {"txType": "buy", "mint": token.mint, "price": 0.01},
                NOW,
            )
            assert event is not None

            state.ingest_source_event(event, active_tokens_loaded=True)

            self.assertEqual(state.storage.load_accepted_market_observations(limit=10), [])
            rejected = state.storage.load_price_observations(limit=10)
            self.assertEqual(len(rejected), 1)
            self.assertFalse(rejected[0].accepted)
            self.assertIn("first observed move", rejected[0].reason)


if __name__ == "__main__":
    unittest.main()

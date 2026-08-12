from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.models import AcceptedMarketObservation, ShadowTrackingCandidate, TokenSignal, TokenStatus, utc_now
from app.core.state import BotState
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


class ShadowCandidatePriorityStateTests(unittest.TestCase):
    def make_state(self, directory: str) -> tuple[BotState, TokenSignal]:
        state = BotState(database_path=str(Path(directory) / "state.db"))
        state.settings.live_max_trade_sol = 0.001
        state.settings.trade_size_sol = 0.001
        state.settings.live_max_slippage_pct = 5
        state.settings.live_priority_fee_cap_sol = 0.0001
        state.settings.max_token_age_seconds = 120
        state.storage.save_settings(state.settings)
        state.current_settings_version_id = state.ensure_settings_version(
            "candidate priority test",
            ["live_max_trade_sol", "trade_size_sol", "max_token_age_seconds"],
        )
        token = TokenSignal(
            id="tok_candidate",
            symbol="CAND",
            name="Candidate",
            mint="MintCandidate111",
            creator="creator",
            detected_at=utc_now(),
            age_seconds=1,
            buy_velocity=0.9,
            sell_pressure=0.1,
            metadata_score=0.9,
            current_price=0.00001,
            score=95,
            status=TokenStatus.PAPER_BOUGHT,
            price_confidence=0.9,
        )
        state.tokens.appendleft(token)
        return state, token

    def accepted_observation(
        self,
        state: BotState,
        token: TokenSignal,
        *,
        mint: str | None = None,
        strategy_version: str | None = None,
        fixture_only: bool = False,
        conflict_state: str = "clear",
        access_state: str = "ready",
        price: float = 0.00001,
    ) -> AcceptedMarketObservation:
        now = utc_now()
        return AcceptedMarketObservation(
            record_id="market_candidate_entry",
            created_at=now,
            schema_version=Storage.SCHEMA_VERSION,
            strategy_id=state.settings.strategy_profile,
            strategy_version=strategy_version or state.current_settings_version_id,
            evidence_mode="paper",
            source="pumpportal",
            source_event_id="source_candidate_entry",
            observed_at=now,
            received_at=now,
            mint=mint or token.mint,
            price=price,
            confidence=0.9,
            acceptance_reason="test accepted trade",
            fixture_only=fixture_only,
            conflict_state=conflict_state,
            access_state=access_state,
        )

    def test_promoted_candidate_waits_for_genuine_entry_before_shadow_quote(self) -> None:
        with TemporaryDirectory() as directory:
            state, token = self.make_state(directory)
            calls: list[dict[str, object]] = []
            state._pumpportal_local_transaction = lambda **kwargs: (calls.append(kwargs) or ({"ok": True}, "dHgi", ""))

            intents = state.generate_live_intents("WalletShadow")
            intent = next(item for item in intents if item["mint"] == token.mint)

            self.assertEqual(intent["status"], "open")
            self.assertEqual(intent["audit_id"], "")
            self.assertEqual(calls, [])
            self.assertEqual(state.preferred_shadow_trade_mints(), [token.mint])

    def test_first_accepted_entry_creates_exactly_one_shadow_audit(self) -> None:
        with TemporaryDirectory() as directory:
            state, token = self.make_state(directory)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            intent_data = next(item for item in state.generate_live_intents("WalletShadow") if item["mint"] == token.mint)
            observation = self.accepted_observation(state, token)
            self.assertTrue(state.storage.save_accepted_market_observation(observation))

            state._activate_waiting_shadow_candidate(observation)
            state._activate_waiting_shadow_candidate(observation)

            stored_intent = state.storage.load_live_intent(str(intent_data["id"]))
            candidate = state.storage.load_shadow_tracking_candidate(f"shadow_candidate_{stored_intent.id}")
            bindings = state.storage.load_shadow_market_evidence_bindings(stored_intent.audit_id)
            self.assertEqual(candidate.state, "tracking_shadow")
            self.assertEqual(len([row for row in bindings if row["role"] == "entry"]), 1)
            self.assertEqual(
                len([audit for audit in state.storage.load_live_execution_audits(20) if audit.mint == token.mint]),
                1,
            )

    def test_ineligible_entry_observations_do_not_activate_candidate(self) -> None:
        cases = (
            {"mint": "WrongMint"},
            {"strategy_version": "set_wrong"},
            {"fixture_only": True},
            {"conflict_state": "conflict"},
            {"access_state": "blocked"},
            {"price": 0.0},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides), TemporaryDirectory() as directory:
                state, token = self.make_state(directory)
                state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
                intent = next(item for item in state.generate_live_intents("WalletShadow") if item["mint"] == token.mint)

                state._activate_waiting_shadow_candidate(self.accepted_observation(state, token, **overrides))

                stored = state.storage.load_live_intent(str(intent["id"]))
                candidate = state.storage.load_shadow_tracking_candidate(f"shadow_candidate_{stored.id}")
                self.assertEqual(stored.audit_id, "")
                self.assertEqual(candidate.state, "awaiting_entry")

    def test_candidate_priority_status_is_redacted_and_respects_cap(self) -> None:
        with TemporaryDirectory() as directory:
            state, token = self.make_state(directory)
            state.settings.max_trade_subscriptions = 1
            state.generate_live_intents("WalletShadow")
            state.source_status.active_trade_subscriptions = 1

            status = state.shadow_candidate_priority_status()
            rendered = str(status).lower()

            self.assertEqual(status["configured_subscription_cap"], 1)
            self.assertEqual(status["active_mint_prefix"], token.mint[:8])
            self.assertTrue(status["cap_respected"])
            self.assertNotIn("wallet", rendered)
            self.assertNotIn("api-key", rendered)
            self.assertNotIn(token.mint.lower(), rendered)

    def test_oldest_active_candidate_keeps_subscription_ownership(self) -> None:
        with TemporaryDirectory() as directory:
            state, first = self.make_state(directory)
            state.generate_live_intents("WalletShadow")
            second = TokenSignal(
                id="tok_candidate_2", symbol="TWO", name="Second", mint="MintCandidate222",
                creator="creator", detected_at=utc_now() + timedelta(seconds=1), age_seconds=1,
                buy_velocity=0.9, sell_pressure=0.1, metadata_score=0.9, current_price=0.00001,
                score=94, status=TokenStatus.PAPER_BOUGHT, price_confidence=0.9,
            )
            second_candidate = ShadowTrackingCandidate(
                candidate_id="shadow_candidate_second", intent_id="intent_second", mint=second.mint,
                strategy_id=state.settings.strategy_profile, strategy_version=state.current_settings_version_id,
                selected_at=utc_now() + timedelta(seconds=1), deadline_at=utc_now() + timedelta(seconds=600),
            )
            state.storage.save_shadow_tracking_candidate(second_candidate)
            state.storage.transition_shadow_tracking_candidate(
                second_candidate.candidate_id, expected_state="awaiting_entry", state="tracking_shadow",
                audit_id="audit_second", deadline_at=utc_now() + timedelta(seconds=600), reason="test",
            )

            self.assertEqual(state.preferred_shadow_trade_mints(), [first.mint])

    def test_blocked_quote_does_not_promote_candidate_to_tracking(self) -> None:
        with TemporaryDirectory() as directory:
            state, token = self.make_state(directory)
            state._pumpportal_local_transaction = lambda **kwargs: ({}, "", "provider blocked")
            intent = next(item for item in state.generate_live_intents("WalletShadow") if item["mint"] == token.mint)
            observation = self.accepted_observation(state, token)

            state._activate_waiting_shadow_candidate(observation)

            candidate = state.storage.load_shadow_tracking_candidate(f"shadow_candidate_{intent['id']}")
            self.assertEqual(candidate.state, "awaiting_entry")
            self.assertEqual(state.storage.count_pending_shadow_audit_captures(candidate.audit_id), 0)

    def test_expired_tracking_candidate_rejects_late_economic_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            state, token = self.make_state(directory)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            intent = next(item for item in state.generate_live_intents("WalletShadow") if item["mint"] == token.mint)
            entry = self.accepted_observation(state, token)
            state.storage.save_accepted_market_observation(entry)
            state._activate_waiting_shadow_candidate(entry)
            stored_intent = state.storage.load_live_intent(str(intent["id"]))
            candidate = state.storage.load_shadow_tracking_candidate(f"shadow_candidate_{stored_intent.id}")
            candidate.deadline_at = utc_now() - timedelta(seconds=1)
            state.storage.transition_shadow_tracking_candidate(
                candidate.candidate_id, expected_state="tracking_shadow", state="tracking_shadow",
                audit_id=candidate.audit_id, deadline_at=candidate.deadline_at, reason="deadline forced",
            )

            state._expire_shadow_tracking_candidates(utc_now())
            late = self.accepted_observation(state, token)
            late.record_id = "market_late"
            late.observed_at = utc_now() + timedelta(seconds=1)
            late.received_at = late.observed_at
            state.storage.save_accepted_market_observation(late)
            inserted = state.storage.bind_accepted_market_observation_to_pending_shadows(late)
            audit = state.storage.load_live_execution_audit(stored_intent.audit_id)

            self.assertEqual(inserted, 0)
            self.assertFalse(state._persist_economic_shadow_comparison(audit))


if __name__ == "__main__":
    unittest.main()

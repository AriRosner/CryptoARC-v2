from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.autonomous_pilot import AutonomousPilotGate, PilotStopEvaluator
from app.core.models import LiveExecutionAudit
from app.core.pilot_risk import PilotRiskPolicy
from app.core.state import BotState


NOW = datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc)
WALLET = "wallet-pilot-1"
SIGNER_MODE = "local_signer_daemon"
SIGNER_ID = "signer-pilot-1"


def complete_inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    authorization = {
        "authorization_id": "autonomous-auth-1",
        "scope": "attended-autonomous-pilot",
        "wallet_public_key": WALLET,
        "signer_mode": SIGNER_MODE,
        "signer_identity_id": SIGNER_ID,
        "attended": True,
        "issued_at": (NOW - timedelta(minutes=2)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=20)).isoformat(),
    }
    readiness = {
        "generated_at": (NOW - timedelta(seconds=20)).isoformat(),
        "full_sniper_gate_ready": True,
        "pilot_readiness_ready": True,
        "wallet_public_key": WALLET,
        "signer_mode": SIGNER_MODE,
        "signer_identity_id": SIGNER_ID,
        "fixture_only": False,
        "unresolved_audits": 0,
        "ledger_debt": 0,
        "backup_fresh": True,
        "kill_switch_available": True,
    }
    policy = {
        "policy_id": "pilot-policy-1",
        "policy_version": "micro-pilot-risk-v1",
        "max_open_positions": 1,
        "automatic_restart_allowed": False,
        "automatic_replenishment_allowed": False,
        "automatic_cap_increase_allowed": False,
    }
    proof = {
        "proof_id": "manual-proof-1",
        "qualified": True,
        "status": "QUALIFIED",
        "wallet_public_key": WALLET,
        "signer_mode": SIGNER_MODE,
        "signer_identity_id": SIGNER_ID,
        "fixture_only": False,
    }
    return authorization, readiness, policy, proof


class AutonomousPilotGateTests(unittest.TestCase):
    def test_complete_actual_inputs_are_eligible_but_do_not_open_authority(self) -> None:
        window = AutonomousPilotGate.open_window(*complete_inputs(), now=NOW)
        self.assertTrue(window.eligible)
        self.assertFalse(window.opened)
        self.assertFalse(window.authority_changed)
        self.assertEqual(window.status, "ELIGIBLE_DEFERRED")
        self.assertEqual(window.max_open_positions, 1)

    def test_requires_fresh_full_and_pilot_gates(self) -> None:
        authorization, readiness, policy, proof = complete_inputs()
        for patch, blocker in (
            ({"generated_at": (NOW - timedelta(minutes=10)).isoformat()}, "readiness_stale"),
            ({"full_sniper_gate_ready": False}, "full_sniper_gate"),
            ({"pilot_readiness_ready": False}, "pilot_readiness_gate"),
            ({"fixture_only": True}, "actual_readiness_required"),
        ):
            with self.subTest(blocker=blocker):
                window = AutonomousPilotGate.open_window(authorization, {**readiness, **patch}, policy, proof, now=NOW)
                self.assertIn(blocker, window.blockers)

    def test_exact_wallet_signer_policy_and_manual_proof_are_required(self) -> None:
        authorization, readiness, policy, proof = complete_inputs()
        cases = (
            ({**authorization, "wallet_public_key": "wrong"}, readiness, policy, proof, "wallet_identity_mismatch"),
            ({**authorization, "signer_identity_id": "wrong"}, readiness, policy, proof, "signer_identity_mismatch"),
            (authorization, readiness, {}, proof, "pilot_policy"),
            (authorization, readiness, policy, {**proof, "qualified": False}, "manual_live_proof"),
        )
        for auth, ready, risk, manual, blocker in cases:
            with self.subTest(blocker=blocker):
                self.assertIn(blocker, AutonomousPilotGate.open_window(auth, ready, risk, manual, now=NOW).blockers)

    def test_window_requires_fresh_scoped_attended_authorization(self) -> None:
        authorization, readiness, policy, proof = complete_inputs()
        cases = (
            ({"scope": "other"}, "authorization_scope"),
            ({"attended": False}, "attended_operator_required"),
            ({"expires_at": (NOW - timedelta(seconds=1)).isoformat()}, "window_expired"),
            ({"authorization_id": ""}, "authorization_id"),
        )
        for patch, blocker in cases:
            with self.subTest(blocker=blocker):
                self.assertIn(blocker, AutonomousPilotGate.open_window({**authorization, **patch}, readiness, policy, proof, now=NOW).blockers)


class PilotStopEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = AutonomousPilotGate.open_window(*complete_inputs(), now=NOW)

    def test_source_conflict_stops_new_entries_without_bypassing_guarded_exit(self) -> None:
        decision = PilotStopEvaluator.evaluate({"type": "source_conflict"}, self.window)
        self.assertTrue(decision.stop_new_entries)
        self.assertEqual(decision.exit_mode, "existing_guarded_exit_only")
        self.assertFalse(decision.automatic_restart_allowed)

    def test_every_approved_stop_condition_closes_new_entry_authority(self) -> None:
        stop_events = (
            "source_loss", "source_conflict", "signer_loss", "identity_mismatch", "quote_stale",
            "simulation_failed", "preflight_failed", "cap_breach", "session_loss_stop",
            "daily_loss_stop", "cumulative_loss_freeze", "drawdown_stop", "consecutive_loss_stop",
            "audit_debt", "ledger_debt", "backup_stale", "kill_switch", "window_expired",
        )
        for event_type in stop_events:
            with self.subTest(event_type=event_type):
                decision = PilotStopEvaluator.evaluate({"type": event_type}, self.window)
                self.assertTrue(decision.stop_new_entries)
                self.assertTrue(decision.close_window)

    def test_normal_observation_does_not_stop(self) -> None:
        decision = PilotStopEvaluator.evaluate({"type": "heartbeat", "healthy": True}, self.window)
        self.assertFalse(decision.stop_new_entries)
        self.assertFalse(decision.close_window)

    def test_end_of_window_requires_kill_disarm_and_reconciliation(self) -> None:
        decision = PilotStopEvaluator.evaluate(
            {"type": "end_window", "kill_switch_enabled": False, "backend_disarmed": False, "reconciled": False},
            self.window,
        )
        self.assertTrue(decision.stop_new_entries)
        self.assertEqual(
            set(decision.blockers),
            {"kill_switch_required", "backend_disarm_required", "reconciliation_required"},
        )
        self.assertTrue(decision.requires_post_run_review)


class AutonomousPilotIntegrationTests(unittest.TestCase):
    def configured_runtime(
        self,
        temp_dir: str,
        *,
        window_ends_at: datetime | None = None,
    ) -> tuple[BotState, dict[str, object], PilotRiskPolicy]:
        state = BotState(str(Path(temp_dir) / "pilot.db"))
        policy = PilotRiskPolicy.create(
            Decimal("200"), Decimal("0.4"), NOW - timedelta(minutes=10),
            reference_observation_id="price-1", settings_version=state.current_settings_version_id,
            operator_intent_id="intent-1",
        )
        state.storage.save_pilot_risk_policy(policy)
        window = {
            "window_id": "runtime-window", "status": "OPEN", "eligible": True, "opened": True,
            "wallet_public_key": WALLET, "signer_mode": SIGNER_MODE, "signer_identity_id": SIGNER_ID,
            "policy_id": policy.policy_id, "manual_proof_id": "manual-proof-1", "attended": True,
            "starts_at": (NOW - timedelta(minutes=2)).isoformat(),
            "ends_at": (window_ends_at or NOW + timedelta(minutes=20)).isoformat(),
        }
        state.storage.save_autonomous_pilot_window(window)
        state.settings.live_active_backend_armed = True
        state.settings.live_active_wallet_public_key = WALLET
        state.settings.live_signer_mode = SIGNER_MODE
        state.settings.kill_switch_enabled = False
        state.storage.save_settings(state.settings)
        state.signer_status = lambda mode, wallet: {
            "connected": True, "healthy": True, "can_unattended_sign": True, "wallet_public_key": WALLET,
        }
        state.source_health = lambda: {"status": "connected", "trust_state": "trusted", "last_event_age_seconds": 0, "live_entry_blocked": False}
        state.manual_live_proof_status = lambda: {
            "qualified": True, "proof_id": "manual-proof-1", "wallet_public_key": WALLET,
            "signer_mode": SIGNER_MODE, "signer_identity_id": SIGNER_ID,
        }
        state.production_rehearsal_status = lambda: {"ready": True, "fixture_only": False}
        state.sentinel_current = lambda refresh=False: {"status": "pilot_eligible", "stale": False}
        state.economic_validation_report = lambda: {"ready": True, "blockers": []}
        return state, window, policy

    def test_live_autonomy_refuses_to_run_without_an_open_pilot_window(self) -> None:
        with TemporaryDirectory() as temp_dir:
            state = BotState(str(Path(temp_dir) / "pilot.db"))
            result = state.run_live_autonomy(True, local_auth_enabled=True)
        self.assertEqual(result["status"], "disabled")
        self.assertIn("no separately authorized attended", result["reason"])
        self.assertFalse(result["pilot_window"]["opened"])

    def test_runtime_guard_revalidates_expiry_source_signer_identity_and_policy(self) -> None:
        with TemporaryDirectory() as temp_dir:
            state, window, policy = self.configured_runtime(temp_dir)
            self.assertEqual(state._pilot_runtime_blockers(window, now=NOW), [])

            expired = {**window, "ends_at": (NOW - timedelta(seconds=1)).isoformat()}
            self.assertIn("window_expired", state._pilot_runtime_blockers(expired, now=NOW))

            state.source_health = lambda: {"status": "connected", "trust_state": "conflicting", "last_event_age_seconds": 0, "live_entry_blocked": True}
            self.assertIn("source_conflict", state._pilot_runtime_blockers(window, now=NOW))
            state.source_health = lambda: {"status": "connected", "trust_state": "trusted", "last_event_age_seconds": 0, "live_entry_blocked": False}

            state.signer_status = lambda mode, wallet: {"connected": False, "healthy": False, "can_unattended_sign": False, "wallet_public_key": WALLET}
            self.assertIn("signer_loss", state._pilot_runtime_blockers(window, now=NOW))
            state.signer_status = lambda mode, wallet: {"connected": True, "healthy": True, "can_unattended_sign": True, "wallet_public_key": WALLET}

            state.settings.live_active_wallet_public_key = "different-wallet"
            self.assertIn("identity_mismatch", state._pilot_runtime_blockers(window, now=NOW))
            state.settings.live_active_wallet_public_key = WALLET

            newer = PilotRiskPolicy.create(
                Decimal("200"), Decimal("0.4"), NOW - timedelta(minutes=1),
                reference_observation_id="price-2", settings_version=state.current_settings_version_id,
                operator_intent_id="intent-2",
            )
            state.storage.save_pilot_risk_policy(newer)
            self.assertNotEqual(newer.policy_id, policy.policy_id)
            self.assertIn("policy_drift", state._pilot_runtime_blockers(window, now=NOW))

    def test_runtime_stop_atomically_closes_window_enables_kill_and_disarms(self) -> None:
        with TemporaryDirectory() as temp_dir:
            state, _window, _policy = self.configured_runtime(temp_dir)
            state.settings.kill_switch_enabled = True
            result = state._enforce_pilot_runtime_guard(now=NOW)

            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "stopped")
            self.assertIn("kill_switch", result["blockers"])
            persisted_window = state.storage.load_latest_autonomous_pilot_window()
            persisted_settings = state.storage.load_settings()
            self.assertEqual(persisted_window["status"], "CLOSED")
            self.assertFalse(persisted_window["active"])
            self.assertTrue(persisted_settings.kill_switch_enabled)
            self.assertFalse(persisted_settings.live_active_backend_armed)
            self.assertEqual(persisted_settings.live_active_wallet_public_key, "")

    def test_expired_window_submit_closes_authority_before_signer_invocation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            state, window, policy = self.configured_runtime(
                temp_dir, window_ends_at=datetime.now(timezone.utc) - timedelta(seconds=1)
            )
            audit = LiveExecutionAudit(
                id="expired-submit", created_at=NOW - timedelta(seconds=10), updated_at=NOW,
                action="buy", mint="mint-1", amount="0.01", status="ready",
                signer_mode=SIGNER_MODE, wallet_public_key=WALLET,
                quote={"unsigned_transaction_base64": "dHgi"},
                pilot_risk_policy_id=policy.policy_id,
                autonomous_pilot_window_id=str(window["window_id"]),
            )
            state.storage.save_live_execution_audit(audit)
            signer_calls: list[str] = []
            state.hot_wallet.simulate_and_submit = lambda *args, **kwargs: signer_calls.append("called") or {}  # type: ignore[method-assign]

            with self.assertRaisesRegex(ValueError, "pilot runtime stop"):
                state.live_submit(audit.id, "")

            self.assertEqual(signer_calls, [])
            self.assertEqual(state.storage.load_latest_autonomous_pilot_window()["status"], "CLOSED")
            self.assertTrue(state.storage.load_settings().kill_switch_enabled)
            self.assertFalse(state.storage.load_settings().live_active_backend_armed)


if __name__ == "__main__":
    unittest.main()

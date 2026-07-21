import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.models import BotStatus, LiveExecutionAudit, TokenSignal, utc_now
from app.core.state import BotState


class DestructiveOperationGuardTests(unittest.TestCase):
    CLEAR_TARGETS = (
        "tokens",
        "events",
        "source_events",
        "backtests",
        "trades",
        "price_observations",
        "strategy_decisions",
        "trade_sessions",
        "settings_versions",
        "experiments",
        "trade_labels",
        "strategy_presets",
        "live_execution_requests",
        "live_sessions",
        "live_execution_audits",
        "live_intents",
        "live_ledger_positions",
        "source_soak_history",
        "all",
    )

    def make_state(self, directory: str) -> BotState:
        state = BotState(database_path=str(Path(directory) / "test.db"))
        state.status = BotStatus.STOPPED
        state.source_status.status = "offline"
        state.solana_logs_status.status = "offline"
        state.settings.live_active_backend_armed = False
        state.settings.kill_switch_enabled = True
        state.storage.save_settings(state.settings)
        return state

    def save_token(self, state: BotState, token_id: str = "tok_guard") -> None:
        state.storage.save_token(
            TokenSignal(
                id=token_id,
                symbol="ARC",
                name="Guard Test",
                mint=f"mint_{token_id}",
                creator="creator_guard",
                detected_at=utc_now(),
                age_seconds=1,
                buy_velocity=0.5,
                sell_pressure=0.1,
                metadata_score=0.9,
                current_price=0.00001,
            )
        )

    def assert_clear_blocked_without_side_effect(self, state: BotState, expected: str) -> None:
        self.save_token(state)
        before = state.data_summary()

        with self.assertRaisesRegex(ValueError, expected):
            state.clear_data("tokens")

        self.assertEqual(state.data_summary(), before)
        self.assertEqual([token.id for token in state.storage.load_tokens()], ["tok_guard"])

    def test_clear_is_blocked_while_bot_or_source_is_running(self) -> None:
        for active_runtime in ("bot", "source", "solana_logs"):
            with self.subTest(active_runtime=active_runtime), TemporaryDirectory() as directory:
                state = self.make_state(directory)
                if active_runtime == "bot":
                    state.status = BotStatus.RUNNING
                elif active_runtime == "source":
                    state.source_status.status = "connected"
                else:
                    state.solana_logs_status.status = "connected"

                self.assert_clear_blocked_without_side_effect(state, "bot and source tasks must be stopped")

    def test_clear_is_blocked_while_live_backend_is_armed(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            state.settings.live_active_backend_armed = True

            self.assert_clear_blocked_without_side_effect(state, "live backend must be disarmed")

    def test_clear_is_blocked_while_kill_switch_is_off(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            state.settings.kill_switch_enabled = False

            self.assert_clear_blocked_without_side_effect(state, "live kill switch must be engaged")

    def test_clear_is_blocked_with_unresolved_live_audit_debt(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="audit_guard",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    action="buy",
                    mint="mint_guard",
                    amount="0.01",
                    status="needs_review",
                    signer_mode="browser_wallet",
                    wallet_public_key="public_wallet",
                )
            )

            self.assert_clear_blocked_without_side_effect(state, "unresolved live audit debt must be zero")

    def test_every_clear_target_is_guarded_including_all(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            state.settings.kill_switch_enabled = False

            for target in self.CLEAR_TARGETS:
                with self.subTest(target=target):
                    with self.assertRaisesRegex(ValueError, "live kill switch must be engaged"):
                        state.clear_data(target)

    def test_restore_guard_runs_before_artifact_handling_and_leaks_no_payload(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            self.save_token(state)
            state.status = BotStatus.RUNNING
            before = state.data_summary()
            artifact = {
                "artifact_type": "cryptoarc_local_backup",
                "format_version": 1,
                "database_base64": "sensitive-marker",
            }

            with self.assertRaises(ValueError) as raised:
                state.confirm_restore_artifact(artifact)

            self.assertIn("bot and source tasks must be stopped", str(raised.exception))
            self.assertNotIn("sensitive-marker", str(raised.exception))
            self.assertEqual(state.data_summary(), before)
            self.assertEqual([token.id for token in state.storage.load_tokens()], ["tok_guard"])

    def test_audit_check_failure_blocks_clear_without_leaking_storage_error(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            self.save_token(state)
            before = state.data_summary()

            def fail_audit_load(limit: int = 100) -> list[LiveExecutionAudit]:
                raise RuntimeError("sensitive-storage-detail")

            state.storage.load_live_execution_audits = fail_audit_load

            with self.assertRaises(ValueError) as raised:
                state.clear_data("tokens")

            self.assertIn("live audit debt could not be verified", str(raised.exception))
            self.assertNotIn("sensitive-storage-detail", str(raised.exception))
            self.assertEqual(state.data_summary(), before)

    def test_safe_prerequisites_allow_clear_and_restore(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            self.save_token(state)
            artifact = state.storage.create_backup_artifact()

            cleared = state.clear_data("tokens")
            restored = state.confirm_restore_artifact(artifact)

            self.assertEqual(cleared["tokens"], 0)
            self.assertEqual(restored["status"], "restored")
            self.assertEqual([token.id for token in state.storage.load_tokens()], ["tok_guard"])

    def test_restore_forces_unsafe_artifact_settings_to_safe_persisted_state(self) -> None:
        with TemporaryDirectory() as directory:
            source = BotState(database_path=str(Path(directory) / "source.db"))
            source.status = BotStatus.RUNNING
            source.settings.live_signer_mode = "browser_wallet"
            source.settings.live_active_backend_armed = True
            source.settings.kill_switch_enabled = False
            source.storage.save_settings(source.settings)
            artifact = source.storage.create_backup_artifact()

            target_path = Path(directory) / "target.db"
            target = BotState(database_path=str(target_path))
            target.status = BotStatus.STOPPED
            target.source_status.status = "offline"
            target.solana_logs_status.status = "offline"
            target.settings.live_active_backend_armed = False
            target.settings.kill_switch_enabled = True
            target.storage.save_settings(target.settings)

            result = target.confirm_restore_artifact(artifact)

            self.assertEqual(result["status"], "restored")
            self.assertEqual(target.status, BotStatus.STOPPED)
            self.assertEqual(target.source_status.status, "offline")
            self.assertEqual(target.solana_logs_status.status, "offline")
            self.assertFalse(target.settings.live_active_backend_armed)
            self.assertTrue(target.settings.kill_switch_enabled)

            reloaded = BotState(database_path=str(target_path))
            self.assertEqual(reloaded.status, BotStatus.STOPPED)
            self.assertFalse(reloaded.settings.live_active_backend_armed)
            self.assertTrue(reloaded.settings.kill_switch_enabled)


if __name__ == "__main__":
    unittest.main()

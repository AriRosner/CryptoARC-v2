import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.models import LiveExecutionAudit, utc_now
from app.core.state import BotState


class ExecutionReadinessQuoteFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = BotState(database_path=str(Path(self.directory.name) / "test.db"))
        self.state.settings.live_max_trade_sol = 0.01
        self.state.settings.live_daily_loss_cap_sol = 0.05
        self.state.settings.live_wallet_exposure_cap_sol = 0.1
        self.state.settings.live_max_open_positions = 1
        self.state.settings.live_max_slippage_pct = 5
        self.state.settings.live_priority_fee_cap_sol = 0.0001
        self.state.storage.save_settings(self.state.settings)
        self.state.ensure_settings_version("settings save", list(self.state.LIVE_CAP_SETTING_KEYS))

    def save_quote_audit(
        self,
        audit_id: str,
        *,
        created_at: datetime,
        status: str = "ready",
        shadow_only: bool = False,
        quote_stale: bool = False,
        quote_error: str = "",
        shadow_comparison: dict[str, object] | None = None,
    ) -> None:
        quote_status = "blocked" if status == "blocked" else "ready"
        self.state.storage.save_live_execution_audit(
            LiveExecutionAudit(
                id=audit_id,
                created_at=created_at,
                updated_at=created_at,
                action="buy",
                mint=f"Mint{audit_id}",
                amount="0.001",
                status=status,
                final_status=status,
                signer_mode="browser_wallet",
                wallet_public_key="WalletFreshness",
                quote={
                    "id": f"quote_{audit_id}",
                    "status": quote_status,
                    "shadow_only": shadow_only,
                    "stale": quote_stale,
                    "error": quote_error,
                },
                shadow_comparison=shadow_comparison or {},
            )
        )

    def execution_readiness(self) -> dict[str, object]:
        return self.state._execution_readiness_status(
            source={
                "trust_state": "trusted",
                "live_entry_blocked": False,
                "shadow_price_observations_blocked": False,
            },
            strategy_promotion={"can_promote": True},
        )

    def gate(self, execution: dict[str, object], gate_id: str) -> dict[str, object]:
        return next(gate for gate in execution["gates"] if gate["id"] == gate_id)

    def test_old_stale_submittable_does_not_poison_recent_shadow_only_health(self) -> None:
        now = utc_now()
        self.save_quote_audit(
            "old_stale",
            created_at=now - timedelta(hours=25),
            status="stale",
            quote_stale=True,
        )
        for index in range(5):
            self.save_quote_audit(
                f"recent_shadow_{index}",
                created_at=now - timedelta(minutes=index + 1),
                shadow_only=True,
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(execution["status"], "shadow_ready")
        self.assertEqual(metrics["quote_attempts"], 6)
        self.assertEqual(metrics["current_quote_attempts"], 5)
        self.assertEqual(metrics["current_quote_health_sample"], 5)
        self.assertEqual(metrics["current_quote_health_sample_kind"], "current_quote_audits")
        self.assertEqual(metrics["current_stale_quotes"], 0)
        self.assertEqual(metrics["current_stale_quote_rate"], 0.0)
        self.assertEqual(execution["current_quote_issues"]["total_issues"], 0)
        self.assertNotIn("stale_quote", execution["policy"]["recommendation"]["inputs"]["issue_categories"])
        self.assertEqual(metrics["loaded_history_quote_attempts"], 6)
        self.assertEqual(metrics["loaded_history_stale_quotes"], 1)
        self.assertEqual(metrics["loaded_history_stale_quote_rate"], 1.0)

    def test_future_and_naive_quote_audits_are_excluded_fail_closed(self) -> None:
        now = utc_now()
        self.save_quote_audit("future", created_at=now + timedelta(minutes=5))
        self.save_quote_audit("naive", created_at=datetime.now())

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(execution["status"], "not_enough_quote_data")
        self.assertFalse(execution["can_shadow"])
        self.assertEqual(execution["current_latest_quote_age_seconds"], None)
        self.assertEqual(metrics["quote_attempts"], 2)
        self.assertEqual(metrics["current_quote_attempts"], 0)
        self.assertEqual(metrics["excluded_future_timestamp_quote_audits"], 1)
        self.assertEqual(metrics["excluded_ambiguous_timestamp_quote_audits"], 1)
        self.assertEqual(metrics["loaded_history_quote_attempts"], 2)
        self.assertEqual(self.gate(execution, "quote_audit_sample")["status"], "fail")

    def test_exactly_five_recent_shadow_only_quotes_clear_quote_health(self) -> None:
        now = utc_now()
        for index in range(5):
            self.save_quote_audit(
                f"shadow_health_{index}",
                created_at=now - timedelta(seconds=index + 1),
                shadow_only=True,
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(execution["status"], "shadow_ready")
        self.assertTrue(execution["can_shadow"])
        self.assertEqual(metrics["quote_attempts"], 5)
        self.assertEqual(metrics["current_quote_attempts"], 5)
        self.assertEqual(metrics["recent_submittable_quote_attempts"], 0)
        self.assertEqual(metrics["current_quote_health_sample"], 5)
        self.assertGreaterEqual(execution["current_latest_quote_age_seconds"], 0)
        self.assertLess(execution["current_latest_quote_age_seconds"], 60)
        self.assertEqual(self.gate(execution, "quote_audit_sample")["status"], "pass")
        self.assertEqual(self.gate(execution, "quote_freshness")["status"], "pass")
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "pass")

    def test_recent_stale_submittable_rate_above_twenty_five_percent_blocks(self) -> None:
        now = utc_now()
        for index in range(5):
            self.save_quote_audit(
                f"recent_submittable_{index}",
                created_at=now - timedelta(seconds=index + 1),
                status="stale" if index < 2 else "ready",
                quote_stale=index < 2,
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(execution["status"], "blocked")
        self.assertFalse(execution["can_shadow"])
        self.assertEqual(metrics["quote_attempts"], 5)
        self.assertEqual(metrics["current_quote_health_sample_kind"], "current_quote_audits")
        self.assertEqual(metrics["current_stale_quotes"], 2)
        self.assertEqual(metrics["current_stale_quote_rate"], 0.4)
        self.assertEqual(self.gate(execution, "quote_freshness")["status"], "fail")

    def test_reconciled_success_with_preserved_stale_metadata_is_not_currently_stale(self) -> None:
        now = utc_now()
        self.save_quote_audit(
            "reconciled_stale_metadata",
            created_at=now - timedelta(seconds=1),
            status="reconciled",
            quote_stale=True,
        )
        for index in range(4):
            self.save_quote_audit(
                f"recent_ready_{index}",
                created_at=now - timedelta(seconds=index + 2),
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_stale_quotes"], 0)
        self.assertEqual(metrics["current_stale_quote_rate"], 0.0)
        self.assertEqual(execution["current_quote_issues"]["stale_count"], 0)
        self.assertEqual(self.gate(execution, "quote_freshness")["status"], "pass")
        self.assertEqual(metrics["loaded_history_stale_quotes"], 1)

    def test_all_history_quote_health_counts_remain_available_additively(self) -> None:
        now = utc_now()
        self.save_quote_audit(
            "old_stale_history",
            created_at=now - timedelta(hours=30),
            status="stale",
            quote_stale=True,
        )
        self.save_quote_audit(
            "old_blocked_history",
            created_at=now - timedelta(hours=29),
            status="blocked",
        )
        self.save_quote_audit(
            "old_shadow_history",
            created_at=now - timedelta(hours=28),
            shadow_comparison={
                "status": "evaluated",
                "outcome": "win",
                "estimated_pnl_sol": 0.001,
                "landing_windows": [],
            },
        )
        for index in range(5):
            self.save_quote_audit(
                f"current_shadow_{index}",
                created_at=now - timedelta(minutes=index + 1),
                shadow_only=True,
            )

        metrics = self.execution_readiness()["metrics"]

        self.assertEqual(metrics["quote_attempts"], 8)
        self.assertEqual(metrics["current_quote_attempts"], 5)
        self.assertEqual(metrics["blocked_quotes"], 1)
        self.assertEqual(metrics["stale_quotes"], 1)
        self.assertEqual(metrics["current_blocked_quotes"], 0)
        self.assertEqual(metrics["current_stale_quotes"], 0)
        self.assertEqual(metrics["shadow_samples"], 6)
        self.assertEqual(metrics["current_shadow_samples"], 5)
        self.assertEqual(metrics["loaded_history_quote_attempts"], 8)
        self.assertEqual(metrics["loaded_history_blocked_quotes"], 1)
        self.assertEqual(metrics["loaded_history_stale_quotes"], 1)
        self.assertEqual(metrics["loaded_history_shadow_samples"], 6)
        self.assertEqual(metrics["loaded_history_blocked_quote_rate"], 0.333)
        self.assertEqual(metrics["loaded_history_stale_quote_rate"], 0.333)

    def test_legacy_calibration_and_latency_metrics_remain_all_history(self) -> None:
        now = utc_now()
        old_created_at = now - timedelta(hours=30)
        self.save_quote_audit("old_timing", created_at=old_created_at)
        old_audit = self.state.storage.load_live_execution_audit("old_timing")
        self.assertIsNotNone(old_audit)
        old_audit.execution_timing = {
            "submitted_at": (old_created_at + timedelta(milliseconds=250)).isoformat(),
            "quote_to_submit_ms": 250,
        }
        self.state.storage.save_live_execution_audit(old_audit)
        for index in range(5):
            self.save_quote_audit(
                f"current_no_timing_{index}",
                created_at=now - timedelta(seconds=index + 1),
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["live_landing_samples"], 1)
        self.assertEqual(metrics["live_quote_to_submit_p50_ms"], 250)
        self.assertEqual(metrics["pipeline_samples"], 1)
        self.assertEqual(metrics["current_live_landing_samples"], 0)
        self.assertEqual(metrics["current_pipeline_samples"], 0)
        self.assertEqual(execution["landing_calibration"]["samples"], 1)
        self.assertEqual(execution["current_landing_calibration"]["samples"], 0)

    def test_five_failed_quotes_fail_the_deduplicated_unhealthy_rate_gate(self) -> None:
        now = utc_now()
        for index in range(5):
            self.save_quote_audit(
                f"failed_{index}",
                created_at=now - timedelta(seconds=index + 1),
                status="failed",
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_failed_quotes"], 5)
        self.assertEqual(metrics["current_unhealthy_quotes"], 5)
        self.assertEqual(metrics["current_unhealthy_quote_rate"], 1.0)
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "fail")
        self.assertFalse(execution["can_shadow"])

    def test_one_failed_quote_in_five_passes_at_twenty_percent(self) -> None:
        now = utc_now()
        for index in range(5):
            self.save_quote_audit(
                f"one_failed_{index}",
                created_at=now - timedelta(seconds=index + 1),
                status="failed" if index == 0 else "ready",
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_failed_quotes"], 1)
        self.assertEqual(metrics["current_unhealthy_quotes"], 1)
        self.assertEqual(metrics["current_unhealthy_quote_rate"], 0.2)
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "pass")

    def test_mixed_failed_and_blocked_quotes_are_deduplicated_at_forty_percent(self) -> None:
        now = utc_now()
        statuses = ["failed", "blocked", "ready", "ready", "ready"]
        for index, status in enumerate(statuses):
            self.save_quote_audit(
                f"mixed_unhealthy_{index}",
                created_at=now - timedelta(seconds=index + 1),
                status=status,
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_failed_quotes"], 1)
        self.assertEqual(metrics["current_blocked_quotes"], 1)
        self.assertEqual(metrics["current_unhealthy_quotes"], 2)
        self.assertEqual(metrics["current_unhealthy_quote_rate"], 0.4)
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "fail")

    def test_unknown_status_with_quote_error_fails_closed(self) -> None:
        now = utc_now()
        for index in range(5):
            self.save_quote_audit(
                f"unknown_error_{index}",
                created_at=now - timedelta(seconds=index + 1),
                status="unknown",
                quote_error="provider returned no transaction",
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_failed_quotes"], 5)
        self.assertEqual(metrics["current_unhealthy_quotes"], 5)
        self.assertEqual(metrics["current_unhealthy_quote_rate"], 1.0)
        self.assertEqual(execution["current_quote_issues"]["failed_count"], 5)
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "fail")

    def test_needs_review_with_quote_error_counts_once_as_unhealthy(self) -> None:
        now = utc_now()
        self.save_quote_audit(
            "needs_review_error",
            created_at=now - timedelta(seconds=1),
            status="needs_review",
            quote_error="confirmation outcome requires review",
        )
        for index in range(4):
            self.save_quote_audit(
                f"needs_review_ready_{index}",
                created_at=now - timedelta(seconds=index + 2),
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_failed_quotes"], 1)
        self.assertEqual(metrics["current_unhealthy_quotes"], 1)
        self.assertEqual(metrics["current_unhealthy_quote_rate"], 0.2)
        self.assertEqual(execution["current_quote_issues"]["failed_count"], 1)
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "pass")

    def test_shadow_only_evidence_never_qualifies_live_submit_eligibility(self) -> None:
        now = utc_now()
        for index in range(5):
            self.save_quote_audit(
                f"live_eligibility_shadow_{index}",
                created_at=now - timedelta(seconds=index + 1),
                shadow_only=True,
            )
        self.state.signer_status = lambda *_args, **_kwargs: {"connected": True}
        self.state._live_execution_blockers = lambda *_args, **_kwargs: []

        execution = self.state._execution_readiness_status(
            source={
                "trust_state": "trusted",
                "live_entry_blocked": False,
                "shadow_price_observations_blocked": False,
            },
            strategy_promotion={"can_promote": True},
            env_live_enabled=True,
            wallet_public_key="WalletFreshness",
        )

        self.assertTrue(execution["can_shadow"])
        self.assertFalse(execution["live_submit_quote_evidence_ready"])
        self.assertFalse(execution["can_live_submit"])

    def test_five_healthy_submittable_quotes_can_qualify_only_with_independent_guards(self) -> None:
        now = utc_now()
        for index in range(5):
            self.save_quote_audit(
                f"live_eligibility_submittable_{index}",
                created_at=now - timedelta(seconds=index + 1),
            )
        self.state.signer_status = lambda *_args, **_kwargs: {"connected": True}
        self.state._live_execution_blockers = lambda *_args, **_kwargs: []
        kwargs = {
            "source": {
                "trust_state": "trusted",
                "live_entry_blocked": False,
                "shadow_price_observations_blocked": False,
            },
            "strategy_promotion": {"can_promote": True},
            "wallet_public_key": "WalletFreshness",
        }

        eligible = self.state._execution_readiness_status(env_live_enabled=True, **kwargs)
        env_disabled = self.state._execution_readiness_status(env_live_enabled=False, **kwargs)
        self.state.signer_status = lambda *_args, **_kwargs: {"connected": False}
        signer_disconnected = self.state._execution_readiness_status(env_live_enabled=True, **kwargs)

        self.assertTrue(eligible["live_submit_quote_evidence_ready"])
        self.assertTrue(eligible["can_live_submit"])
        self.assertFalse(env_disabled["can_live_submit"])
        self.assertFalse(signer_disconnected["can_live_submit"])

    def test_pending_final_status_does_not_mask_adverse_audit_statuses(self) -> None:
        now = utc_now()
        adverse = [
            ("failed", False),
            ("stale", True),
            ("blocked", False),
        ]
        for index, (status, quote_stale) in enumerate(adverse):
            audit = LiveExecutionAudit(
                id=f"pending_masks_{status}",
                created_at=now - timedelta(seconds=index + 1),
                updated_at=now - timedelta(seconds=index + 1),
                action="buy",
                mint=f"MintPending{status}",
                amount="0.001",
                status=status,
                signer_mode="browser_wallet",
                wallet_public_key="WalletFreshness",
                quote={
                    "id": f"quote_pending_masks_{status}",
                    "status": "blocked" if status == "blocked" else "ready",
                    "shadow_only": False,
                    "stale": quote_stale,
                },
            )
            self.assertEqual(audit.final_status, "pending")
            self.state.storage.save_live_execution_audit(audit)
        for index in range(2):
            self.save_quote_audit(
                f"pending_masks_ready_{index}",
                created_at=now - timedelta(seconds=index + 4),
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_failed_quotes"], 1)
        self.assertEqual(metrics["current_stale_quotes"], 1)
        self.assertEqual(metrics["current_blocked_quotes"], 1)
        self.assertEqual(metrics["current_unhealthy_quotes"], 2)
        self.assertEqual(metrics["current_unhealthy_quote_rate"], 0.4)
        self.assertEqual(self.gate(execution, "quote_freshness")["status"], "pass")
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "fail")

    def test_pending_and_unknown_outcomes_are_indeterminate_and_unhealthy(self) -> None:
        now = utc_now()
        for index, status in enumerate(["pending", "unknown", "pending", "unknown", "pending"]):
            self.state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id=f"indeterminate_{index}",
                    created_at=now - timedelta(seconds=index + 1),
                    updated_at=now - timedelta(seconds=index + 1),
                    action="buy",
                    mint=f"MintIndeterminate{index}",
                    amount="0.001",
                    status=status,
                    final_status=status,
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletFreshness",
                    quote={
                        "id": f"quote_indeterminate_{index}",
                        "status": status,
                        "shadow_only": False,
                    },
                )
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_ready_quotes"], 0)
        self.assertEqual(metrics["current_failed_quotes"], 5)
        self.assertEqual(metrics["current_unhealthy_quote_rate"], 1.0)
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "fail")
        self.assertFalse(execution["live_submit_quote_evidence_ready"])

    def test_quote_ready_metadata_alone_cannot_advance_pending_audit_lifecycle(self) -> None:
        now = utc_now()
        for index in range(5):
            self.state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id=f"quote_ready_only_{index}",
                    created_at=now - timedelta(seconds=index + 1),
                    updated_at=now - timedelta(seconds=index + 1),
                    action="buy",
                    mint=f"MintQuoteReadyOnly{index}",
                    amount="0.001",
                    status="pending",
                    final_status="pending",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletFreshness",
                    quote={
                        "id": f"quote_ready_only_{index}",
                        "status": "ready",
                        "shadow_only": False,
                    },
                )
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_ready_quotes"], 0)
        self.assertEqual(metrics["current_unhealthy_quotes"], 5)
        self.assertEqual(metrics["current_submittable_ready_quotes"], 0)
        self.assertFalse(execution["live_submit_quote_evidence_ready"])
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "fail")

    def test_quote_terminal_metadata_alone_cannot_advance_pending_audit_lifecycle(self) -> None:
        now = utc_now()
        for index, quote_status in enumerate(["confirmed", "reconciled"]):
            self.state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id=f"quote_terminal_only_{quote_status}",
                    created_at=now - timedelta(seconds=index + 1),
                    updated_at=now - timedelta(seconds=index + 1),
                    action="buy",
                    mint=f"MintQuoteTerminalOnly{quote_status}",
                    amount="0.001",
                    status="pending",
                    final_status="pending",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletFreshness",
                    quote={
                        "id": f"quote_terminal_only_{quote_status}",
                        "status": quote_status,
                        "shadow_only": False,
                    },
                )
            )
        for index in range(3):
            self.save_quote_audit(
                f"quote_terminal_only_ready_{index}",
                created_at=now - timedelta(seconds=index + 3),
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_ready_quotes"], 3)
        self.assertEqual(metrics["current_unhealthy_quotes"], 2)
        self.assertEqual(metrics["current_unhealthy_quote_rate"], 0.4)
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "fail")

    def test_shadow_ttl_stale_does_not_exempt_independent_failure_or_provider_error(self) -> None:
        now = utc_now()
        self.save_quote_audit(
            "shadow_stale_failed",
            created_at=now - timedelta(seconds=1),
            status="failed",
            shadow_only=True,
            quote_stale=True,
        )
        self.save_quote_audit(
            "shadow_stale_provider_error",
            created_at=now - timedelta(seconds=2),
            status="stale",
            shadow_only=True,
            quote_stale=True,
            quote_error="provider unavailable",
        )
        for index in range(3):
            self.save_quote_audit(
                f"shadow_stale_independent_ready_{index}",
                created_at=now - timedelta(seconds=index + 3),
                shadow_only=True,
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_stale_quotes"], 0)
        self.assertEqual(metrics["current_failed_quotes"], 2)
        self.assertEqual(metrics["current_unhealthy_quotes"], 2)
        self.assertEqual(metrics["current_unhealthy_quote_rate"], 0.4)
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "fail")

    def test_failed_shadow_quotes_are_included_in_shadow_health_population(self) -> None:
        now = utc_now()
        self.save_quote_audit(
            "mixed_population_submittable_ready",
            created_at=now - timedelta(seconds=1),
        )
        for index in range(4):
            self.save_quote_audit(
                f"mixed_population_shadow_failed_{index}",
                created_at=now - timedelta(seconds=index + 2),
                status="failed",
                shadow_only=True,
            )

        execution = self.execution_readiness()
        metrics = execution["metrics"]

        self.assertEqual(metrics["current_quote_health_sample"], 5)
        self.assertEqual(metrics["current_unhealthy_quotes"], 4)
        self.assertEqual(metrics["current_unhealthy_quote_rate"], 0.8)
        self.assertEqual(metrics["current_submittable_quote_health_sample"], 1)
        self.assertEqual(metrics["current_submittable_unhealthy_quotes"], 0)
        self.assertEqual(self.gate(execution, "failed_quote_rate")["status"], "fail")
        self.assertFalse(execution["can_shadow"])

    def test_audit_history_truncation_blocks_readiness_fail_closed(self) -> None:
        now = utc_now()
        for index in range(501):
            self.save_quote_audit(
                f"history_limit_{index:03d}",
                created_at=now - timedelta(seconds=index + 1),
            )

        execution = self.execution_readiness()

        self.assertEqual(execution["audit_history_limit"], 500)
        self.assertTrue(execution["audit_history_truncated"])
        self.assertFalse(execution["audit_history_complete"])
        self.assertEqual(execution["metrics"]["quote_attempts"], 500)
        self.assertEqual(self.gate(execution, "audit_history_complete")["status"], "fail")
        self.assertFalse(execution["can_shadow"])
        self.assertTrue(any("history" in blocker.lower() for blocker in execution["blockers"]))

    def test_terminal_success_overrides_stale_error_metadata_in_current_diagnostics(self) -> None:
        now = utc_now()
        self.state.storage.save_live_execution_audit(
            LiveExecutionAudit(
                id="terminal_success_stale_error",
                created_at=now - timedelta(seconds=1),
                updated_at=now - timedelta(seconds=1),
                action="buy",
                mint="MintTerminalSuccess",
                amount="0.001",
                status="failed",
                final_status="reconciled",
                signer_mode="browser_wallet",
                wallet_public_key="WalletFreshness",
                quote={
                    "id": "quote_terminal_success_stale_error",
                    "status": "stale",
                    "stale": True,
                    "error": "historical provider timeout",
                    "shadow_only": False,
                },
                errors=["historical provider timeout"],
                reconciliation_status="matched",
            )
        )
        for index in range(4):
            self.save_quote_audit(
                f"terminal_success_ready_{index}",
                created_at=now - timedelta(seconds=index + 2),
            )

        execution = self.execution_readiness()

        self.assertEqual(execution["metrics"]["current_ready_quotes"], 5)
        self.assertEqual(execution["metrics"]["current_unhealthy_quotes"], 0)
        self.assertEqual(execution["current_quote_issues"]["total_issues"], 0)
        self.assertEqual(execution["current_failure_stages"]["total_failures"], 0)


if __name__ == "__main__":
    unittest.main()

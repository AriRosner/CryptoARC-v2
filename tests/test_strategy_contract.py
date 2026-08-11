from __future__ import annotations

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.storage import Storage
from app.core.strategy import DecisionPipeline
from app.core.strategy_contract import SniperDecision, SniperStrategyVersion
from app.core.risk import RiskEngine


STRATEGY = {
    "strategy_id": "sniper",
    "strategy_version": "sniper-v1",
    "eligible_venues": ["pumpfun"],
    "token_programs": ["spl-token", "token-2022"],
    "token_age": {"min_seconds": 0, "max_seconds": 90},
    "entry_window": {"start_seconds": 0, "end_seconds": 60},
    "liquidity": {"min_sol": 20.0, "max_price_impact_pct": 3.0},
    "authorities": {"allow_mint_authority": False, "allow_freeze_authority": False},
    "concentration": {"max_creator_pct": 10.0, "max_holder_pct": 15.0, "required_if_trustworthy": True},
    "source": {"max_age_seconds": 5, "min_confidence": 0.8},
    "entry": {"min_score": 75, "abstain_on_missing": True},
    "exits": {
        "minimum_hold_seconds": 5,
        "take_profit_pct": 20.0,
        "stop_loss_pct": 8.0,
        "trailing_stop_pct": 5.0,
        "break_even_pct": 10.0,
        "stalled_trade_seconds": 45,
        "maximum_hold_seconds": 180,
    },
    "execution": {
        "quote_lifetime_seconds": 3,
        "slippage_cap_pct": 3.0,
        "priority_fee_cap_sol": 0.0005,
        "total_cost_cap_sol": 0.002,
    },
    "exposure": {"max_positions": 1, "max_exposure_sol": 0.05},
    "stops": {
        "session_loss_sol": 0.05,
        "daily_loss_sol": 0.05,
        "cumulative_drawdown_sol": 0.125,
        "consecutive_losses": 3,
    },
}


EVIDENCE = {
    "venue": "pumpfun",
    "token_program": "spl-token",
    "token_age_seconds": 20,
    "entry_window_seconds": 20,
    "liquidity_sol": 25.0,
    "price_impact_pct": 1.0,
    "mint_authority_active": False,
    "freeze_authority_active": False,
    "concentration_trustworthy": True,
    "creator_hold_pct": 4.0,
    "max_holder_pct": 7.0,
    "source_age_seconds": 1,
    "source_confidence": 0.95,
    "score": 82,
    "quote_age_seconds": 1,
    "slippage_pct": 1.0,
    "priority_fee_sol": 0.0001,
    "total_cost_sol": 0.001,
}


SESSION = {
    "active_strategy_version": "sniper-v1",
    "open_positions": 0,
    "exposure_sol": 0.0,
    "session_loss_sol": 0.0,
    "daily_loss_sol": 0.0,
    "cumulative_drawdown_sol": 0.0,
    "consecutive_losses": 0,
}


class StrategyContractTests(unittest.TestCase):
    def test_canonical_hash_is_stable_across_input_order_and_mutation(self) -> None:
        first_payload = copy.deepcopy(STRATEGY)
        reversed_payload = dict(reversed(list(copy.deepcopy(STRATEGY).items())))
        first = SniperStrategyVersion.from_dict(first_payload)
        second = SniperStrategyVersion.from_dict(reversed_payload)
        first_payload["entry"]["min_score"] = 1

        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.fingerprint(), second.fingerprint())
        self.assertEqual(first.to_dict()["entry"]["min_score"], 75)

    def test_unknown_and_missing_fields_are_rejected(self) -> None:
        missing = copy.deepcopy(STRATEGY)
        missing["execution"].pop("total_cost_cap_sol")
        unknown = copy.deepcopy(STRATEGY)
        unknown["surprise"] = True

        with self.assertRaisesRegex(ValueError, "missing fields"):
            SniperStrategyVersion.from_dict(missing)
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            SniperStrategyVersion.from_dict(unknown)

    def test_missing_required_evidence_abstains_with_stable_reason(self) -> None:
        evidence = copy.deepcopy(EVIDENCE)
        evidence["liquidity_sol"] = None

        decision = SniperDecision.evaluate(SniperStrategyVersion.from_dict(STRATEGY), evidence, SESSION)

        self.assertEqual(decision.action, "abstain")
        self.assertEqual(decision.reasons, ("required_liquidity_missing",))
        self.assertEqual(decision.strategy_version, "sniper-v1")

    def test_required_source_and_entry_filters_fail_closed(self) -> None:
        cases = {
            "source_stale": {"source_age_seconds": 6},
            "source_confidence_below_minimum": {"source_confidence": 0.2},
            "token_too_old": {"token_age_seconds": 91},
            "liquidity_below_minimum": {"liquidity_sol": 19.0},
            "price_impact_above_maximum": {"price_impact_pct": 3.1},
            "mint_authority_rejected": {"mint_authority_active": True},
            "freeze_authority_rejected": {"freeze_authority_active": True},
            "creator_concentration_above_maximum": {"creator_hold_pct": 11.0},
            "holder_concentration_above_maximum": {"max_holder_pct": 16.0},
            "score_below_minimum": {"score": 74},
            "slippage_above_cap": {"slippage_pct": 3.1},
            "priority_fee_above_cap": {"priority_fee_sol": 0.0006},
            "total_cost_above_cap": {"total_cost_sol": 0.0021},
        }
        strategy = SniperStrategyVersion.from_dict(STRATEGY)
        for blocker, patch in cases.items():
            with self.subTest(blocker=blocker):
                evidence = {**EVIDENCE, **patch}
                result = SniperDecision.evaluate(strategy, evidence, SESSION)
                self.assertEqual(result.action, "abstain")
                self.assertIn(blocker, result.reasons)

    def test_session_stops_and_changed_version_require_restart(self) -> None:
        strategy = SniperStrategyVersion.from_dict(STRATEGY)
        cases = {
            "strategy_version_changed_restart_required": {"active_strategy_version": "sniper-v0"},
            "maximum_positions_reached": {"open_positions": 1},
            "maximum_exposure_reached": {"exposure_sol": 0.05},
            "session_loss_stop": {"session_loss_sol": 0.05},
            "daily_loss_stop": {"daily_loss_sol": 0.05},
            "cumulative_drawdown_stop": {"cumulative_drawdown_sol": 0.125},
            "consecutive_loss_stop": {"consecutive_losses": 3},
        }
        for blocker, patch in cases.items():
            with self.subTest(blocker=blocker):
                result = SniperDecision.evaluate(strategy, EVIDENCE, {**SESSION, **patch})
                self.assertEqual(result.action, "abstain")
                self.assertIn(blocker, result.reasons)

    def test_risk_engine_exposes_the_same_immutable_session_boundaries(self) -> None:
        reasons = RiskEngine.contract_session_reasons(
            SniperStrategyVersion.from_dict(STRATEGY).to_dict(),
            {**SESSION, "open_positions": 1, "daily_loss_sol": 0.05},
        )

        self.assertEqual(reasons, ("maximum_positions_reached", "daily_loss_stop"))

    def test_passing_decision_is_deterministic_intent_only_with_all_exits(self) -> None:
        strategy = SniperStrategyVersion.from_dict(STRATEGY)
        first = SniperDecision.evaluate(strategy, EVIDENCE, SESSION)
        second = SniperDecision.evaluate(strategy, copy.deepcopy(EVIDENCE), copy.deepcopy(SESSION))

        self.assertEqual(first, second)
        self.assertEqual(first.action, "intent")
        self.assertEqual(first.score, 82)
        self.assertEqual(first.exits, STRATEGY["exits"])
        self.assertNotIn("signer", first.to_dict())
        self.assertNotIn("transaction", first.to_dict())

    def test_pipeline_exposes_versioned_evaluation_without_replacing_existing_flow(self) -> None:
        pipeline = DecisionPipeline()
        decision = pipeline.evaluate_sniper(SniperStrategyVersion.from_dict(STRATEGY), EVIDENCE, SESSION)

        self.assertEqual(decision.action, "intent")
        self.assertEqual(pipeline.ENGINE_VERSION, "strategy-v3")

    def test_storage_persists_immutable_versions_and_rejects_content_reuse(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "strategy.db"))
            strategy = SniperStrategyVersion.from_dict(STRATEGY)
            self.assertTrue(storage.save_sniper_strategy_version(strategy))
            self.assertFalse(storage.save_sniper_strategy_version(strategy))
            changed = copy.deepcopy(STRATEGY)
            changed["entry"]["min_score"] = 76
            with self.assertRaisesRegex(ValueError, "different content"):
                storage.save_sniper_strategy_version(SniperStrategyVersion.from_dict(changed))
            loaded = storage.load_sniper_strategy_versions(limit=10)

        self.assertEqual(loaded, [strategy])


if __name__ == "__main__":
    unittest.main()

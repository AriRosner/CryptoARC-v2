from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from app.core.risk import RiskEngine


_SECTIONS: dict[str, set[str]] = {
    "token_age": {"min_seconds", "max_seconds"},
    "entry_window": {"start_seconds", "end_seconds"},
    "liquidity": {"min_sol", "max_price_impact_pct"},
    "authorities": {"allow_mint_authority", "allow_freeze_authority"},
    "concentration": {"max_creator_pct", "max_holder_pct", "required_if_trustworthy"},
    "source": {"max_age_seconds", "min_confidence"},
    "entry": {"min_score", "abstain_on_missing"},
    "exits": {
        "minimum_hold_seconds",
        "take_profit_pct",
        "stop_loss_pct",
        "trailing_stop_pct",
        "break_even_pct",
        "stalled_trade_seconds",
        "maximum_hold_seconds",
    },
    "execution": {"quote_lifetime_seconds", "slippage_cap_pct", "priority_fee_cap_sol", "total_cost_cap_sol"},
    "exposure": {"max_positions", "max_exposure_sol"},
    "stops": {"session_loss_sol", "daily_loss_sol", "cumulative_drawdown_sol", "consecutive_losses"},
}
_TOP_LEVEL = {"strategy_id", "strategy_version", "eligible_venues", "token_programs", *_SECTIONS.keys()}


@dataclass(frozen=True, slots=True)
class SniperStrategyVersion:
    strategy_id: str
    strategy_version: str
    _canonical: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "SniperStrategyVersion":
        data = json.loads(json.dumps(dict(payload)))
        missing = _TOP_LEVEL - set(data)
        unknown = set(data) - _TOP_LEVEL
        if missing:
            raise ValueError(f"missing fields: {', '.join(sorted(missing))}")
        if unknown:
            raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
        for section, expected in _SECTIONS.items():
            value = data.get(section)
            if not isinstance(value, dict):
                raise ValueError(f"{section} must be an object")
            section_missing = expected - set(value)
            section_unknown = set(value) - expected
            if section_missing:
                raise ValueError(f"missing fields in {section}: {', '.join(sorted(section_missing))}")
            if section_unknown:
                raise ValueError(f"unknown fields in {section}: {', '.join(sorted(section_unknown))}")
        cls._validate_values(data)
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return cls(str(data["strategy_id"]), str(data["strategy_version"]), canonical)

    @staticmethod
    def _validate_values(data: dict[str, object]) -> None:
        for key in ("strategy_id", "strategy_version"):
            if not isinstance(data[key], str) or not str(data[key]).strip():
                raise ValueError(f"{key} must be a non-empty string")
        for key in ("eligible_venues", "token_programs"):
            values = data[key]
            if not isinstance(values, list) or not values or any(not isinstance(item, str) or not item for item in values):
                raise ValueError(f"{key} must be a non-empty string list")
        token_age = data["token_age"]
        entry_window = data["entry_window"]
        assert isinstance(token_age, dict) and isinstance(entry_window, dict)
        SniperStrategyVersion._range(token_age, "min_seconds", "max_seconds", "token_age")
        SniperStrategyVersion._range(entry_window, "start_seconds", "end_seconds", "entry_window")
        if float(entry_window["end_seconds"]) > float(token_age["max_seconds"]):
            raise ValueError("entry_window must fit within token_age")
        for section, key, minimum, maximum in (
            ("liquidity", "min_sol", 0.0, None),
            ("liquidity", "max_price_impact_pct", 0.0, 100.0),
            ("concentration", "max_creator_pct", 0.0, 100.0),
            ("concentration", "max_holder_pct", 0.0, 100.0),
            ("source", "max_age_seconds", 0.0, None),
            ("source", "min_confidence", 0.0, 1.0),
            ("entry", "min_score", 0.0, 100.0),
            ("execution", "quote_lifetime_seconds", 0.0, None),
            ("execution", "slippage_cap_pct", 0.0, 100.0),
            ("execution", "priority_fee_cap_sol", 0.0, None),
            ("execution", "total_cost_cap_sol", 0.0, None),
            ("exposure", "max_positions", 1.0, None),
            ("exposure", "max_exposure_sol", 0.0, None),
            ("stops", "session_loss_sol", 0.0, None),
            ("stops", "daily_loss_sol", 0.0, None),
            ("stops", "cumulative_drawdown_sol", 0.0, None),
            ("stops", "consecutive_losses", 1.0, None),
        ):
            section_data = data[section]
            assert isinstance(section_data, dict)
            SniperStrategyVersion._number(section_data[key], f"{section}.{key}", minimum, maximum)
        exits = data["exits"]
        assert isinstance(exits, dict)
        for key, value in exits.items():
            SniperStrategyVersion._number(value, f"exits.{key}", 0.0, None)
        if float(exits["maximum_hold_seconds"]) < float(exits["minimum_hold_seconds"]):
            raise ValueError("maximum hold must not precede minimum hold")
        for section, keys in (("authorities", ("allow_mint_authority", "allow_freeze_authority")), ("concentration", ("required_if_trustworthy",)), ("entry", ("abstain_on_missing",))):
            section_data = data[section]
            assert isinstance(section_data, dict)
            for key in keys:
                if not isinstance(section_data[key], bool):
                    raise ValueError(f"{section}.{key} must be boolean")

    @staticmethod
    def _range(data: dict[str, object], low: str, high: str, label: str) -> None:
        SniperStrategyVersion._number(data[low], f"{label}.{low}", 0.0, None)
        SniperStrategyVersion._number(data[high], f"{label}.{high}", 0.0, None)
        if float(data[high]) < float(data[low]):
            raise ValueError(f"{label} maximum must not precede minimum")

    @staticmethod
    def _number(value: object, label: str, minimum: float, maximum: float | None) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} must be numeric")
        numeric = float(value)
        if numeric < minimum or (maximum is not None and numeric > maximum):
            raise ValueError(f"{label} is outside its allowed range")

    def canonical_json(self) -> str:
        return self._canonical

    def fingerprint(self) -> str:
        return hashlib.sha256(self._canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return json.loads(self._canonical)


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    action: str
    score: int
    reasons: tuple[str, ...]
    strategy_id: str
    strategy_version: str
    strategy_fingerprint: str
    exits: dict[str, object]
    intent: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "score": self.score,
            "reasons": list(self.reasons),
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_fingerprint": self.strategy_fingerprint,
            "exits": dict(self.exits),
            "intent": dict(self.intent),
        }


class SniperDecision:
    @staticmethod
    def evaluate(
        strategy: SniperStrategyVersion,
        evidence: Mapping[str, object],
        session_state: Mapping[str, object],
    ) -> StrategyDecision:
        config = strategy.to_dict()
        reasons: list[str] = []
        required = {
            "venue": "required_venue_missing",
            "token_program": "required_token_program_missing",
            "token_age_seconds": "required_token_age_missing",
            "entry_window_seconds": "required_entry_window_missing",
            "liquidity_sol": "required_liquidity_missing",
            "price_impact_pct": "required_price_impact_missing",
            "mint_authority_active": "required_mint_authority_missing",
            "freeze_authority_active": "required_freeze_authority_missing",
            "concentration_trustworthy": "required_concentration_trust_missing",
            "source_age_seconds": "required_source_age_missing",
            "source_confidence": "required_source_confidence_missing",
            "score": "required_score_missing",
            "quote_age_seconds": "required_quote_age_missing",
            "slippage_pct": "required_slippage_missing",
            "priority_fee_sol": "required_priority_fee_missing",
            "total_cost_sol": "required_total_cost_missing",
        }
        for field_name, blocker in required.items():
            if evidence.get(field_name) is None:
                reasons.append(blocker)
        concentration = config["concentration"]
        assert isinstance(concentration, dict)
        if evidence.get("concentration_trustworthy") is True:
            if evidence.get("creator_hold_pct") is None:
                reasons.append("required_creator_concentration_missing")
            if evidence.get("max_holder_pct") is None:
                reasons.append("required_holder_concentration_missing")
        elif concentration["required_if_trustworthy"] and evidence.get("concentration_trustworthy") is not False:
            reasons.append("concentration_evidence_untrustworthy")
        if reasons:
            return SniperDecision._result(strategy, evidence, config, reasons)

        token_age = config["token_age"]
        entry_window = config["entry_window"]
        liquidity = config["liquidity"]
        authorities = config["authorities"]
        source = config["source"]
        entry = config["entry"]
        execution = config["execution"]
        assert all(isinstance(item, dict) for item in (token_age, entry_window, liquidity, authorities, source, entry, execution))
        checks = (
            (evidence["venue"] not in config["eligible_venues"], "venue_ineligible"),
            (evidence["token_program"] not in config["token_programs"], "token_program_ineligible"),
            (float(evidence["token_age_seconds"]) < float(token_age["min_seconds"]), "token_too_new"),
            (float(evidence["token_age_seconds"]) > float(token_age["max_seconds"]), "token_too_old"),
            (float(evidence["entry_window_seconds"]) < float(entry_window["start_seconds"]), "entry_window_not_open"),
            (float(evidence["entry_window_seconds"]) > float(entry_window["end_seconds"]), "entry_window_closed"),
            (float(evidence["liquidity_sol"]) < float(liquidity["min_sol"]), "liquidity_below_minimum"),
            (float(evidence["price_impact_pct"]) > float(liquidity["max_price_impact_pct"]), "price_impact_above_maximum"),
            (evidence["mint_authority_active"] is True and authorities["allow_mint_authority"] is False, "mint_authority_rejected"),
            (evidence["freeze_authority_active"] is True and authorities["allow_freeze_authority"] is False, "freeze_authority_rejected"),
            (float(evidence.get("creator_hold_pct") or 0) > float(concentration["max_creator_pct"]), "creator_concentration_above_maximum"),
            (float(evidence.get("max_holder_pct") or 0) > float(concentration["max_holder_pct"]), "holder_concentration_above_maximum"),
            (float(evidence["source_age_seconds"]) > float(source["max_age_seconds"]), "source_stale"),
            (float(evidence["source_confidence"]) < float(source["min_confidence"]), "source_confidence_below_minimum"),
            (int(evidence["score"]) < int(entry["min_score"]), "score_below_minimum"),
            (float(evidence["quote_age_seconds"]) > float(execution["quote_lifetime_seconds"]), "quote_expired"),
            (float(evidence["slippage_pct"]) > float(execution["slippage_cap_pct"]), "slippage_above_cap"),
            (float(evidence["priority_fee_sol"]) > float(execution["priority_fee_cap_sol"]), "priority_fee_above_cap"),
            (float(evidence["total_cost_sol"]) > float(execution["total_cost_cap_sol"]), "total_cost_above_cap"),
        )
        reasons.extend(reason for failed, reason in checks if failed)
        reasons.extend(RiskEngine.contract_session_reasons(config, session_state))
        return SniperDecision._result(strategy, evidence, config, reasons)

    @staticmethod
    def _result(
        strategy: SniperStrategyVersion,
        evidence: Mapping[str, object],
        config: dict[str, object],
        reasons: list[str],
    ) -> StrategyDecision:
        score = int(evidence.get("score") or 0)
        action = "abstain" if reasons else "intent"
        return StrategyDecision(
            action=action,
            score=score,
            reasons=tuple(dict.fromkeys(reasons)),
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            strategy_fingerprint=strategy.fingerprint(),
            exits=dict(config["exits"]),
            intent={"action": "buy", "strategy_version": strategy.strategy_version} if action == "intent" else {},
        )

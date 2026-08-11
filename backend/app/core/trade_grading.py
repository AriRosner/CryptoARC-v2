from __future__ import annotations

import hashlib
import json

from app.core.models import TradeGrade, TradeRevision


class DeterministicTradeGrader:
    VERSION = "deterministic-trade-grader-v1"
    MODES = frozenset({"paper", "shadow", "manual_live", "autonomous_live"})
    EX_POST_ONLY = frozenset(
        {"pnl_sol", "exit_compliant", "exit_reason", "post_exit_peak", "max_favorable_excursion", "max_adverse_excursion"}
    )

    @classmethod
    def grade(cls, revision: TradeRevision) -> TradeGrade:
        if revision.mode not in cls.MODES:
            raise ValueError(f"unsupported evidence mode: {revision.mode}")
        ex_ante = {key: value for key, value in revision.ex_ante_facts.items() if key not in cls.EX_POST_ONLY}
        ex_post = dict(revision.ex_post_facts)
        signal_score = cls._number(ex_ante.get("signal_score"))
        source_confidence = cls._number(ex_ante.get("source_confidence"))
        latency_ms = cls._number(ex_ante.get("latency_ms"))
        slippage_pct = cls._number(ex_ante.get("slippage_pct"))
        pnl_sol = cls._number(ex_post.get("pnl_sol"))

        classifications = {
            "entry": cls._boolean_quality(ex_ante.get("entry_compliant")),
            "signal": "good" if signal_score >= 75 else "warning" if signal_score >= 50 else "poor",
            "risk": cls._boolean_quality(ex_ante.get("risk_clear")),
            "source": "good" if source_confidence >= 0.8 else "warning" if source_confidence >= 0.6 else "poor",
            "execution": "good" if latency_ms <= 500 and slippage_pct <= 1 else "warning" if latency_ms <= 1500 and slippage_pct <= 3 else "poor",
            "exit": cls._boolean_quality(ex_post.get("exit_compliant")),
            "outcome": "good" if pnl_sol > 0 else "warning" if pnl_sol == 0 else "poor",
        }
        present = sum(
            1
            for value in (
                ex_ante.get("signal_score"), ex_ante.get("entry_compliant"), ex_ante.get("risk_clear"),
                ex_ante.get("source_confidence"), ex_ante.get("latency_ms"), ex_ante.get("slippage_pct"),
                ex_post.get("pnl_sol"), ex_post.get("exit_compliant"),
            )
            if value is not None
        )
        evidence_factor = min(1.0, len(revision.evidence_ids) / 3)
        confidence = round((present / 8) * evidence_factor, 4)
        identity = {
            "revision": revision.to_dict(),
            "grader_version": cls.VERSION,
            "classifications": classifications,
        }
        grade_id = "grade_" + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        reasons = tuple(f"{name}:{value}" for name, value in classifications.items())
        return TradeGrade(
            grade_id=grade_id,
            trade_id=revision.trade_id,
            revision_id=revision.revision_id,
            mode=revision.mode,
            created_at=revision.completed_at,
            grader_version=cls.VERSION,
            rules_version=revision.rules_version,
            strategy_version=revision.strategy_version,
            data_schema_version=revision.data_schema_version,
            classifications=classifications,
            ex_ante_facts=ex_ante,
            ex_post_facts=ex_post,
            evidence_ids=revision.evidence_ids,
            confidence=confidence,
            reasons=reasons,
        )

    @staticmethod
    def _number(value: object) -> float:
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _boolean_quality(value: object) -> str:
        if value is True:
            return "good"
        if value is False:
            return "poor"
        return "unknown"

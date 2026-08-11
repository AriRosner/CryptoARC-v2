from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.core.models import CandidateValidation, PromotionResult, StrategyCandidate


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class CandidateFactory:
    @staticmethod
    def propose(
        base_version: dict[str, Any] | object,
        patch: dict[str, Any],
        evidence_ids: tuple[str, ...] | list[str],
        *,
        now: datetime | None = None,
    ) -> StrategyCandidate:
        if not patch or not evidence_ids:
            raise ValueError("candidate patch and attributable evidence IDs are required")
        if isinstance(base_version, dict):
            base_payload = dict(base_version)
            base_id = str(base_payload.get("strategy_version") or base_payload.get("version") or "unversioned")
        elif hasattr(base_version, "to_dict"):
            base_payload = base_version.to_dict()
            base_id = str(base_payload.get("strategy_version") or "unversioned")
        else:
            raise TypeError("base strategy version must be a versioned strategy payload")
        identity = {
            "base": base_payload,
            "patch": patch,
            "evidence_ids": sorted(set(str(value) for value in evidence_ids if str(value))),
        }
        fingerprint = hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()
        return StrategyCandidate(
            candidate_id=f"candidate_{fingerprint[:24]}",
            base_strategy_version=base_id,
            proposed_strategy_version=f"candidate-{fingerprint[:12]}",
            created_at=now or datetime.now(timezone.utc),
            patch=json.loads(_canonical(patch)),
            evidence_ids=tuple(identity["evidence_ids"]),
            fingerprint=fingerprint,
        )


class CandidateValidator:
    MIN_REPLAY_SAMPLES = 100
    MIN_SHADOW_SAMPLES = 100

    @classmethod
    def compare(
        cls,
        incumbent: dict[str, Any],
        candidate: StrategyCandidate,
        replay: dict[str, Any],
        walk_forward: dict[str, Any],
        shadow: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> CandidateValidation:
        blockers: list[str] = []
        if bool(replay.get("evidence_leakage")):
            blockers.append("evidence_leakage")
        if int(replay.get("sample_size") or 0) < cls.MIN_REPLAY_SAMPLES:
            blockers.append("replay_sample_below_100")
        train_net = float(walk_forward.get("train_net") or 0.0)
        validation_net = float(walk_forward.get("validation_net") or 0.0)
        if train_net <= 0 or validation_net < train_net * 0.25:
            blockers.append("walk_forward_collapse")
        if int(shadow.get("sample_size") or 0) < cls.MIN_SHADOW_SAMPLES:
            blockers.append("shadow_sample_below_100")
        if not bool(shadow.get("genuine")):
            blockers.append("genuine_shadow_required")
        if not bool(shadow.get("version_matched")):
            blockers.append("strategy_version_mismatch")
        if float(shadow.get("tail_loss") or 0.0) < float(incumbent.get("tail_loss") or 0.0):
            blockers.append("tail_loss_worse_than_incumbent")
        if float(shadow.get("max_drawdown") or 0.0) > float(incumbent.get("max_drawdown") or 0.0):
            blockers.append("drawdown_worse_than_incumbent")
        if float(shadow.get("exit_success_rate") or 0.0) < float(incumbent.get("exit_success_rate") or 0.0):
            blockers.append("exit_quality_worse_than_incumbent")
        if float(shadow.get("net_after_costs") or 0.0) <= float(incumbent.get("net_after_costs") or 0.0):
            blockers.append("all_cost_result_not_better")
        deduped = tuple(dict.fromkeys(blockers))
        metrics = {
            "incumbent": dict(incumbent),
            "replay": dict(replay),
            "walk_forward": dict(walk_forward),
            "shadow": dict(shadow),
        }
        identity = {"candidate_id": candidate.candidate_id, "blockers": deduped, "metrics": metrics}
        fingerprint = hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()
        return CandidateValidation(
            validation_id=f"candidate_validation_{fingerprint[:24]}",
            candidate_id=candidate.candidate_id,
            created_at=now or datetime.now(timezone.utc),
            accepted=not deduped,
            blockers=deduped,
            metrics=metrics,
        )


class PromotionGate:
    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def promote(
        self,
        candidate_id: str,
        operator_intent_id: str,
        *,
        now: datetime,
        active_session_id: str = "",
    ) -> PromotionResult:
        if active_session_id:
            return PromotionResult(candidate_id, False, "active_session")
        if not operator_intent_id.strip():
            return PromotionResult(candidate_id, False, "operator_intent_required")
        candidate = self.storage.load_strategy_candidate(candidate_id)
        if candidate is None:
            return PromotionResult(candidate_id, False, "candidate_not_found")
        selection = self.storage.load_active_strategy_selection()
        if selection and selection.get("candidate_id") == candidate_id and selection.get("operator_intent_id") == operator_intent_id:
            return PromotionResult(candidate_id, True, idempotent=True, promotion_id=str(selection.get("promotion_id") or ""))
        validation = self.storage.load_latest_candidate_validation(candidate_id)
        if validation is None or not validation.accepted:
            return PromotionResult(candidate_id, False, "validation_blocked")
        promotion_id = "promotion_" + hashlib.sha256(
            _canonical({"candidate_id": candidate_id, "intent": operator_intent_id}).encode("utf-8")
        ).hexdigest()[:24]
        promoted = self.storage.promote_strategy_candidate(candidate, validation, promotion_id, operator_intent_id, now)
        return PromotionResult(candidate_id, promoted, "" if promoted else "stale_promotion", False, promotion_id if promoted else "")

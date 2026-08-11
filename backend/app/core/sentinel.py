from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from app.core.models import SentinelInputs, SentinelThresholds, SentinelVerdict


class Sentinel:
    """Pure, deterministic conditions assessment with no execution authority."""

    STATUSES = frozenset({"ready", "warning", "blocker"})

    @staticmethod
    def evaluate(inputs: SentinelInputs, thresholds: SentinelThresholds, now: datetime) -> SentinelVerdict:
        now = Sentinel._utc(now)
        insufficient: list[str] = []
        blockers: list[str] = []
        warnings: list[str] = []

        if not inputs.strategy_id or not inputs.strategy_version or not inputs.input_version:
            insufficient.append("strategy and input identity must be complete")
        if not inputs.evidence:
            insufficient.append("no attributable evidence is available")

        for item in inputs.evidence:
            observed_at = Sentinel._utc(item.observed_at)
            if not item.name or not item.evidence_ids:
                insufficient.append(f"{item.name or 'unnamed'} evidence is not attributable")
            if item.conflicting:
                insufficient.append(f"{item.name} evidence conflicts")
            if observed_at > now:
                insufficient.append(f"{item.name} evidence is future-dated")
            if (now - observed_at).total_seconds() > thresholds.max_evidence_age_seconds:
                insufficient.append(f"{item.name} evidence is stale")
            if item.expires_at is not None and Sentinel._utc(item.expires_at) <= now:
                insufficient.append(f"{item.name} evidence is expired")
            if item.sample_size < thresholds.min_sample_size:
                insufficient.append(
                    f"{item.name} sample size {item.sample_size} is below {thresholds.min_sample_size}"
                )
            if item.status not in Sentinel.STATUSES:
                insufficient.append(f"{item.name} has unknown status {item.status}")
            elif item.status == "blocker":
                blockers.append(item.reason or f"{item.name} is unfavorable")
            elif item.status == "warning":
                warnings.append(item.reason or f"{item.name} requires observation")

        if insufficient:
            status = "insufficient_evidence"
            blockers = insufficient + blockers
            reasons = tuple(insufficient)
        elif blockers:
            status = "unfavorable"
            reasons = tuple(blockers)
        elif warnings:
            status = "observe_only"
            reasons = tuple(warnings)
        else:
            status = "pilot_eligible"
            reasons = ("all supplied version-matched conditions evidence meets the recorded thresholds",)

        sample_size = sum(max(0, item.sample_size) for item in inputs.evidence)
        confidence = Sentinel._confidence(inputs, thresholds, bool(insufficient))
        expires_at = now + timedelta(seconds=max(1, thresholds.validity_seconds))
        identity = {
            "created_at": now.isoformat(),
            "strategy_id": inputs.strategy_id,
            "strategy_version": inputs.strategy_version,
            "input_version": inputs.input_version,
            "status": status,
            "inputs": inputs.to_dict(),
            "thresholds": thresholds.to_dict(),
        }
        verdict_id = "sentinel_" + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        return SentinelVerdict(
            verdict_id=verdict_id,
            status=status,
            created_at=now,
            expires_at=expires_at,
            strategy_id=inputs.strategy_id,
            strategy_version=inputs.strategy_version,
            input_version=inputs.input_version,
            inputs=inputs.to_dict(),
            thresholds=thresholds.to_dict(),
            sample_size=sample_size,
            confidence=confidence,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
            reasons=reasons,
        )

    @staticmethod
    def _confidence(inputs: SentinelInputs, thresholds: SentinelThresholds, invalid: bool) -> float:
        if invalid or not inputs.evidence:
            return 0.0
        sample_ratio = min(1.0, min(item.sample_size for item in inputs.evidence) / max(1, thresholds.min_sample_size))
        status_ratio = min({"ready": 1.0, "warning": 0.7, "blocker": 0.4}.get(item.status, 0.0) for item in inputs.evidence)
        return round(sample_ratio * status_ratio, 4)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

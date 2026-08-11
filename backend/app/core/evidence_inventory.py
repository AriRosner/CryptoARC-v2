from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Mapping


class EvidenceInventory:
    """Build a read-only, fail-closed summary from already-produced reports."""

    DEFERRED_PHYSICAL_EVIDENCE = (
        "genuine source soak",
        "all-cost shadow campaign",
        "production deployment rehearsal",
        "manual-live proof",
        "attended autonomous-live pilot",
        "post-run scale/hold/revise/stop decision",
    )

    @staticmethod
    def build(
        repo_head: str,
        origin_main: str,
        reports: Mapping[str, object],
        *,
        merge_base: str = "",
        dirty: bool | None = None,
    ) -> dict[str, object]:
        report_data = deepcopy(dict(reports))
        readiness = EvidenceInventory._mapping(report_data.get("readiness"))
        live = EvidenceInventory._mapping(report_data.get("live"))
        evidence_mode = EvidenceInventory._mapping(report_data.get("evidence_mode"))
        pilot = EvidenceInventory._mapping(report_data.get("pilot"))
        post_run = EvidenceInventory._mapping(report_data.get("post_run"))
        source = EvidenceInventory._mapping(report_data.get("source"))
        active_strategy = EvidenceInventory._mapping(report_data.get("active_strategy"))
        promotion = EvidenceInventory._mapping(readiness.get("strategy_promotion"))

        clean_head = str(repo_head or "").strip()
        clean_origin_main = str(origin_main or "").strip()
        clean_merge_base = str(merge_base or "").strip()
        exact_main_state_captured = bool(
            clean_head and clean_origin_main and clean_merge_base and dirty is not None
        )
        origin_main_is_ancestor = bool(
            exact_main_state_captured and clean_merge_base == clean_origin_main
        )

        observations = [
            item
            for item in EvidenceInventory._list(source.get("observations"))
            if isinstance(item, Mapping)
        ]
        fixture_observations = [item for item in observations if item.get("fixture_only") is True]
        genuine_observations = [
            item
            for item in observations
            if item.get("fixture_only") is not True and item.get("accepted") is True
        ]
        rejected_observations = [
            item
            for item in observations
            if item.get("fixture_only") is not True and item.get("accepted") is not True
        ]

        modes = [
            item
            for item in EvidenceInventory._list(evidence_mode.get("modes"))
            if isinstance(item, Mapping)
        ]
        shadow = next((item for item in modes if item.get("mode") == "shadow"), {})
        shadow_samples = EvidenceInventory._integer(shadow.get("samples"))
        evaluated_shadow_samples = EvidenceInventory._integer(shadow.get("evaluated"))

        source_adapters = [
            deepcopy(dict(item))
            for item in EvidenceInventory._list(report_data.get("source_adapters"))
            if isinstance(item, Mapping)
        ]
        source_access_state = str(source.get("access_state") or "unknown")
        backup = EvidenceInventory._mapping(live.get("pre_run_backup"))
        age_seconds = EvidenceInventory._number_or_none(backup.get("age_seconds"))
        signer = EvidenceInventory._mapping(live.get("signer"))
        signer_mode = str(pilot.get("signer_mode") or signer.get("mode") or "unknown")

        blockers: list[str] = []
        if not exact_main_state_captured:
            blockers.append("exact Git state was not supplied")
        elif dirty:
            blockers.append("worktree is dirty")
        if exact_main_state_captured and not origin_main_is_ancestor:
            blockers.append("origin/main is not the captured merge-base ancestor")
        if source_access_state != "ready":
            blockers.append(f"source access is {source_access_state}")

        EvidenceInventory._extend_strings(blockers, readiness.get("recommended_actions"))
        EvidenceInventory._extend_strings(blockers, promotion.get("blockers"))
        execution = EvidenceInventory._mapping(readiness.get("execution_readiness"))
        EvidenceInventory._extend_strings(blockers, execution.get("blockers"))
        EvidenceInventory._extend_strings(blockers, live.get("blockers"))
        EvidenceInventory._extend_strings(blockers, evidence_mode.get("contamination_warnings"))
        EvidenceInventory._extend_strings(blockers, pilot.get("blockers"))
        EvidenceInventory._extend_strings(blockers, post_run.get("action_items"))
        blockers = list(dict.fromkeys(blockers))

        strategy_fingerprint = str(
            active_strategy.get("fingerprint")
            or promotion.get("strategy_fingerprint")
            or "unknown"
        )
        strategy_id = str(
            active_strategy.get("id")
            or active_strategy.get("profile")
            or promotion.get("profile")
            or "unknown"
        )
        strategy_version = str(
            active_strategy.get("version")
            or strategy_fingerprint
            or "unknown"
        )

        return {
            "artifact_type": "cryptoarc_evidence_inventory",
            "format_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "code_state": {
                "head": clean_head,
                "origin_main": clean_origin_main,
                "merge_base": clean_merge_base,
                "dirty": dirty,
                "origin_main_is_ancestor": origin_main_is_ancestor,
                "exact_main_state_captured": exact_main_state_captured,
            },
            "active_strategy": {
                "id": strategy_id,
                "version": strategy_version,
                "fingerprint": strategy_fingerprint,
                "promotion_status": str(promotion.get("status") or "unknown"),
            },
            "source_access": {
                "state": source_access_state,
                "adapters": source_adapters,
            },
            "evidence": {
                "genuine_source_observations": len(genuine_observations),
                "fixture_source_observations": len(fixture_observations),
                "rejected_source_observations": len(rejected_observations),
                "shadow_samples": shadow_samples,
                "evaluated_shadow_samples": evaluated_shadow_samples,
                "mode_separation_status": str(evidence_mode.get("status") or "unknown"),
            },
            "operations": {
                "backup_state": str(backup.get("state") or "unknown"),
                "backup_age_hours": round(age_seconds / 3600, 3) if age_seconds is not None else None,
                "signer_mode": signer_mode,
                "signer_status": str(signer.get("status") or "unknown"),
                "post_run_status": str(post_run.get("status") or "unknown"),
            },
            "machine_verifiable_readiness": {
                "ready": not blockers,
                "readiness_status": str(readiness.get("status") or "unknown"),
                "pilot_status": str(pilot.get("status") or "unknown"),
                "blockers": blockers,
            },
            "deferred_physical_evidence": list(EvidenceInventory.DEFERRED_PHYSICAL_EVIDENCE),
            "authority": {
                "live_trading_enabled": live.get("env_live_enabled") is True,
                "authority_changed": False,
                "read_only": True,
            },
            "privacy_note": (
                "Inventory contains Git identifiers and redacted readiness summaries only; "
                "it must not contain credentials, seeds, private keys, signer material, or auth tokens."
            ),
        }

    @staticmethod
    def _mapping(value: object) -> Mapping[str, object]:
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _list(value: object) -> list[object]:
        return list(value) if isinstance(value, (list, tuple)) else []

    @staticmethod
    def _integer(value: object) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _number_or_none(value: object) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extend_strings(target: list[str], values: object) -> None:
        for value in EvidenceInventory._list(values):
            clean = str(value or "").strip()
            if clean:
                target.append(clean)

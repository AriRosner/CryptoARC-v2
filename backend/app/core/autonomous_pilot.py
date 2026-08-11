from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping


STOP_EVENTS = frozenset(
    {
        "source_loss",
        "source_conflict",
        "signer_loss",
        "identity_mismatch",
        "quote_stale",
        "simulation_failed",
        "preflight_failed",
        "cap_breach",
        "session_loss_stop",
        "daily_loss_stop",
        "cumulative_loss_freeze",
        "drawdown_stop",
        "consecutive_loss_stop",
        "audit_debt",
        "ledger_debt",
        "backup_stale",
        "kill_switch",
        "window_expired",
    }
)


def _timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _zero(value: object) -> bool:
    try:
        return int(value or 0) == 0
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class PilotWindow:
    window_id: str
    status: str
    eligible: bool
    opened: bool
    blockers: tuple[str, ...]
    authorization_id: str
    wallet_public_key: str
    signer_mode: str
    signer_identity_id: str
    policy_id: str
    manual_proof_id: str
    starts_at: str
    ends_at: str
    attended: bool
    max_open_positions: int
    automatic_restart_allowed: bool = False
    automatic_replenishment_allowed: bool = False
    automatic_cap_increase_allowed: bool = False
    authority_changed: bool = False
    operator_action: str = "Pilot window creation remains disabled pending a separate physical authorization window."

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


@dataclass(frozen=True, slots=True)
class StopDecision:
    stop_new_entries: bool
    close_window: bool
    exit_mode: str
    blockers: tuple[str, ...]
    automatic_restart_allowed: bool = False
    requires_kill_switch: bool = False
    requires_backend_disarm: bool = False
    requires_reconciliation: bool = False
    requires_post_run_review: bool = False
    authority_changed: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


class AutonomousPilotGate:
    """Evaluate a proposed attended window without opening execution authority."""

    @classmethod
    def open_window(
        cls,
        authorization: Mapping[str, object],
        readiness_snapshot: Mapping[str, object],
        policy: Mapping[str, object],
        manual_proof: Mapping[str, object],
        *,
        now: datetime | None = None,
    ) -> PilotWindow:
        checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        blockers: list[str] = []

        def block(value: str) -> None:
            if value not in blockers:
                blockers.append(value)

        authorization_id = str(authorization.get("authorization_id") or "").strip()
        wallet = str(authorization.get("wallet_public_key") or "").strip()
        signer_mode = str(authorization.get("signer_mode") or "").strip()
        signer_id = str(authorization.get("signer_identity_id") or "").strip()
        issued_at = _timestamp(authorization.get("issued_at"))
        expires_at = _timestamp(authorization.get("expires_at"))
        if not authorization_id:
            block("authorization_id")
        if authorization.get("scope") != "attended-autonomous-pilot":
            block("authorization_scope")
        if authorization.get("attended") is not True:
            block("attended_operator_required")
        if issued_at is None or issued_at > checked_at or checked_at - issued_at > timedelta(hours=1):
            block("authorization_not_fresh")
        if expires_at is None or expires_at <= checked_at:
            block("window_expired")
        elif issued_at is None or expires_at - issued_at > timedelta(minutes=30):
            block("window_too_long")

        generated_at = _timestamp(readiness_snapshot.get("generated_at"))
        if generated_at is None or generated_at > checked_at or checked_at - generated_at > timedelta(minutes=2):
            block("readiness_stale")
        if readiness_snapshot.get("full_sniper_gate_ready") is not True:
            block("full_sniper_gate")
        if readiness_snapshot.get("pilot_readiness_ready") is not True:
            block("pilot_readiness_gate")
        if readiness_snapshot.get("fixture_only") is not False:
            block("actual_readiness_required")
        if not _zero(readiness_snapshot.get("unresolved_audits")):
            block("audit_debt")
        if not _zero(readiness_snapshot.get("ledger_debt")):
            block("ledger_debt")
        if readiness_snapshot.get("backup_fresh") is not True:
            block("backup_stale")
        if readiness_snapshot.get("kill_switch_available") is not True:
            block("kill_switch_unavailable")
        if readiness_snapshot.get("prior_pilot_window_id") and readiness_snapshot.get("prior_post_pilot_review_clear") is not True:
            block("post_pilot_review_required")

        identities = (readiness_snapshot, manual_proof)
        if not wallet or any(str(item.get("wallet_public_key") or "") != wallet for item in identities):
            block("wallet_identity_mismatch")
        if not signer_mode or any(str(item.get("signer_mode") or "") != signer_mode for item in identities):
            block("signer_mode_mismatch")
        if not signer_id or any(str(item.get("signer_identity_id") or "") != signer_id for item in identities):
            block("signer_identity_mismatch")

        policy_id = str(policy.get("policy_id") or "").strip()
        if (
            not policy_id
            or policy.get("policy_version") != "micro-pilot-risk-v1"
            or policy.get("max_open_positions") != 1
            or policy.get("automatic_restart_allowed") is not False
            or policy.get("automatic_replenishment_allowed") is not False
            or policy.get("automatic_cap_increase_allowed") is not False
        ):
            block("pilot_policy")
        manual_proof_id = str(manual_proof.get("proof_id") or "").strip()
        if manual_proof.get("qualified") is not True or manual_proof.get("fixture_only") is not False or not manual_proof_id:
            block("manual_live_proof")

        identity = json.dumps(
            {"authorization_id": authorization_id, "policy_id": policy_id, "proof_id": manual_proof_id},
            sort_keys=True,
            separators=(",", ":"),
        )
        window_id = f"pilot_window_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
        eligible = not blockers
        return PilotWindow(
            window_id=window_id,
            status="ELIGIBLE_DEFERRED" if eligible else "BLOCKED",
            eligible=eligible,
            opened=False,
            blockers=tuple(blockers),
            authorization_id=authorization_id,
            wallet_public_key=wallet,
            signer_mode=signer_mode,
            signer_identity_id=signer_id,
            policy_id=policy_id,
            manual_proof_id=manual_proof_id,
            starts_at=checked_at.isoformat(),
            ends_at=expires_at.isoformat() if expires_at else "",
            attended=authorization.get("attended") is True,
            max_open_positions=1,
        )


class PilotStopEvaluator:
    @classmethod
    def evaluate(cls, event: Mapping[str, object], state: PilotWindow | Mapping[str, object]) -> StopDecision:
        event_type = str(event.get("type") or "")
        eligible = state.eligible if isinstance(state, PilotWindow) else bool(state.get("eligible"))
        if event_type == "end_window":
            blockers: list[str] = []
            if event.get("kill_switch_enabled") is not True:
                blockers.append("kill_switch_required")
            if event.get("backend_disarmed") is not True:
                blockers.append("backend_disarm_required")
            if event.get("reconciled") is not True:
                blockers.append("reconciliation_required")
            return StopDecision(
                True,
                True,
                "existing_guarded_exit_only",
                tuple(blockers),
                requires_kill_switch=True,
                requires_backend_disarm=True,
                requires_reconciliation=True,
                requires_post_run_review=True,
            )
        should_stop = event_type in STOP_EVENTS or not eligible
        return StopDecision(
            stop_new_entries=should_stop,
            close_window=should_stop,
            exit_mode="existing_guarded_exit_only" if should_stop else "guarded_entry_and_exit",
            blockers=(event_type or "inactive_window",) if should_stop else (),
            requires_kill_switch=should_stop,
            requires_backend_disarm=should_stop,
            requires_reconciliation=should_stop,
            requires_post_run_review=should_stop,
        )

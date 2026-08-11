from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Mapping


PASS_FIELDS = (
    "password_restart",
    "totp_restart",
    "bearer_only",
    "wallet_signer_match",
    "signer_rotation_invalidation",
    "signer_loss_disarm",
    "source_loss_entry_block",
    "protective_exit_prepared",
    "kill_switch",
    "fresh_backup",
    "restore_preview",
    "restore_smoke",
    "schema_match",
    "restart_recovery",
    "notification_disclosure",
)

SAFE_EVIDENCE_FIELDS = frozenset(
    (
        "fixture_only",
        "physical_window_authorized",
        "authorization_id",
        "authorization_expires_at",
        *PASS_FIELDS,
        "unresolved_audits",
        "ledger_debt",
        "tailnet_only",
        "public_exposure",
        "image_size_risk_accepted",
        "image_size_risk_acceptance_expires_at",
        "evidence_ids",
    )
)

EVIDENCE_ID_GATES = (*PASS_FIELDS, "tailnet_only", "public_exposure", "image_size_risk_accepted")
EVIDENCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,199}$")


def _fresh(value: object, now: datetime) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return False
    return parsed.astimezone(timezone.utc) > now


def _zero(value: object) -> bool:
    try:
        return int(value or 0) == 0
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class RehearsalGate:
    gate_id: str
    passed: bool
    evidence_value: object
    physical: bool = False


@dataclass(frozen=True, slots=True)
class RehearsalReport:
    ready: bool
    blockers: tuple[str, ...]
    gates: tuple[RehearsalGate, ...]
    evidence: dict[str, object]
    fixture_only: bool
    authority_changed: bool = False
    operator_action: str = "Complete deferred physical checks in a separately authorized window."

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["gates"] = [asdict(gate) for gate in self.gates]
        return payload


class ProductionGateRehearsal:
    """Fail-closed aggregation of already-captured production rehearsal evidence."""

    @classmethod
    def evaluate(
        cls,
        evidence: Mapping[str, object],
        *,
        now: datetime | None = None,
    ) -> RehearsalReport:
        evaluated_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        safe = {key: evidence[key] for key in SAFE_EVIDENCE_FIELDS if key in evidence and key != "evidence_ids"}
        raw_ids = evidence.get("evidence_ids")
        evidence_ids = raw_ids if isinstance(raw_ids, Mapping) else {}
        safe["evidence_ids"] = {
            key: value
            for key, value in evidence_ids.items()
            if key in EVIDENCE_ID_GATES and isinstance(value, str) and EVIDENCE_ID_PATTERN.fullmatch(value)
        }
        fixture_only = evidence.get("fixture_only") is not False
        gates: list[RehearsalGate] = []

        def add(gate_id: str, passed: bool, value: object, *, physical: bool = False) -> None:
            gates.append(RehearsalGate(gate_id, bool(passed), value, physical))

        add("physical_rehearsal_required", not fixture_only, not fixture_only, physical=True)
        add("physical_window_authorized", evidence.get("physical_window_authorized") is True, evidence.get("physical_window_authorized"), physical=True)
        add("physical_authorization_id", bool(str(evidence.get("authorization_id") or "").strip()), bool(str(evidence.get("authorization_id") or "").strip()), physical=True)
        add("physical_authorization_expired", _fresh(evidence.get("authorization_expires_at"), evaluated_at), evidence.get("authorization_expires_at"), physical=True)
        for key in PASS_FIELDS:
            add(key, evidence.get(key) == "pass", evidence.get(key), physical=True)
        add("unresolved_audit_debt", _zero(evidence.get("unresolved_audits")), evidence.get("unresolved_audits"))
        add("ledger_debt", _zero(evidence.get("ledger_debt")), evidence.get("ledger_debt"))
        add("tailnet_only", evidence.get("tailnet_only") is True, evidence.get("tailnet_only"), physical=True)
        add("public_exposure", evidence.get("public_exposure") is False, evidence.get("public_exposure"), physical=True)
        add("image_size_risk_accepted", evidence.get("image_size_risk_accepted") is True, evidence.get("image_size_risk_accepted"))
        add(
            "image_size_risk_acceptance_expired",
            _fresh(evidence.get("image_size_risk_acceptance_expires_at"), evaluated_at),
            evidence.get("image_size_risk_acceptance_expires_at"),
        )
        for gate_id in EVIDENCE_ID_GATES:
            add(f"{gate_id}_evidence_id", gate_id in safe["evidence_ids"], gate_id in safe["evidence_ids"], physical=True)
        blockers = tuple(gate.gate_id for gate in gates if not gate.passed)
        return RehearsalReport(
            ready=not blockers,
            blockers=blockers,
            gates=tuple(gates),
            evidence=safe,
            fixture_only=fixture_only,
            operator_action=(
                "Production rehearsal evidence is complete; live authority remains unchanged."
                if not blockers
                else "Complete deferred physical checks in a separately authorized window."
            ),
        )

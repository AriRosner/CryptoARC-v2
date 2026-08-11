from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence


def _count(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class PostPilotReview:
    review_id: str
    window_id: str
    clear: bool
    status: str
    blockers: tuple[str, ...]
    next_pilot_blocked: bool
    allowed_decisions: tuple[str, ...]
    audit_ids: tuple[str, ...]
    transaction_signatures: tuple[str, ...]
    grade_count: int
    performance: dict[str, object]
    cumulative_loss_usd: str
    automatic_scaling_applied: bool = False
    authority_changed: bool = False
    operator_action: str = "Record one append-only operator decision; scaling requires a later reviewed design."

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["allowed_decisions"] = list(self.allowed_decisions)
        payload["audit_ids"] = list(self.audit_ids)
        payload["transaction_signatures"] = list(self.transaction_signatures)
        return payload


@dataclass(frozen=True, slots=True)
class PilotOperatorDecision:
    decision_id: str
    review_id: str
    decision: str
    rationale: str
    authorization_id: str
    created_at: str
    scaling_applied: bool = False
    authority_changed: bool = False
    operator_action: str = "Decision recorded as intent only; no wallet, cap, strategy, or authority changed."

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PilotReview:
    @classmethod
    def close(
        cls,
        window: Mapping[str, object],
        audits: Sequence[Mapping[str, object]],
        ledger: Mapping[str, object],
        grades: Sequence[Mapping[str, object]],
        performance: Mapping[str, object],
    ) -> PostPilotReview:
        blockers: list[str] = []

        def block(value: str) -> None:
            if value not in blockers:
                blockers.append(value)

        window_id = str(window.get("window_id") or "").strip()
        if not window_id or window.get("status") != "CLOSED" or window.get("opened") is not True:
            block("window_not_closed")
        if window.get("ended_with_kill_switch") is not True:
            block("kill_switch_incomplete")
        if window.get("backend_disarmed") is not True:
            block("backend_disarm_incomplete")
        if window.get("reconciled") is not True:
            block("window_reconciliation_incomplete")

        audit_ids: list[str] = []
        signatures: list[str] = []
        for audit in audits:
            audit_id = str(audit.get("audit_id") or "").strip()
            signature = str(audit.get("transaction_signature") or "").strip()
            if audit_id:
                audit_ids.append(audit_id)
            if signature:
                signatures.append(signature)
            if not signature or audit.get("explained") is not True:
                block("unexplained_transaction")
            if audit.get("cap_bypass") is True:
                block("cap_bypass")
            if audit.get("status") != "reconciled" or audit.get("reconciliation_complete") is not True:
                block("reconciliation_incomplete")
            if audit.get("fees_complete") is not True:
                block("fees_incomplete")
            if audit.get("pnl_complete") is not True:
                block("pnl_incomplete")
        if not audits:
            block("audit_evidence_missing")

        wallet = str(window.get("wallet_public_key") or "")
        if not wallet or str(ledger.get("wallet_public_key") or "") != wallet:
            block("wallet_identity_mismatch")
        if ledger.get("balances_explained") is not True:
            block("balance_unexplained")
        if ledger.get("fees_complete") is not True:
            block("fees_incomplete")
        if ledger.get("pnl_complete") is not True:
            block("pnl_incomplete")
        if _count(ledger.get("open_positions")) != 0:
            block("unresolved_position")
        if _count(ledger.get("unresolved_audits")) != 0:
            block("audit_debt")
        if _count(ledger.get("ledger_debt")) != 0:
            block("ledger_debt")
        if _count(ledger.get("unknown_transactions")) != 0:
            block("unexplained_transaction")
        if ledger.get("manual_database_repair") is True:
            block("manual_database_repair")
        cumulative_loss = _decimal(ledger.get("cumulative_loss_usd"))
        if cumulative_loss is None:
            block("cumulative_loss_unknown")
        elif cumulative_loss >= Decimal("25"):
            block("cumulative_loss_freeze")

        metric_names = ("drawdown", "fills", "latency", "exits", "caps")
        for metric in metric_names:
            if performance.get(f"{metric}_complete") is not True:
                block(f"{metric}_incomplete")
        graded_ids = {str(grade.get("trade_id") or "") for grade in grades if grade.get("status") == "graded"}
        if not set(audit_ids).issubset(graded_ids):
            block("grades_incomplete")

        identity = json.dumps(
            {"window_id": window_id, "audit_ids": sorted(audit_ids), "signatures": sorted(signatures)},
            sort_keys=True,
            separators=(",", ":"),
        )
        review_id = f"post_pilot_review_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
        clear = not blockers
        return PostPilotReview(
            review_id=review_id,
            window_id=window_id,
            clear=clear,
            status="CLEAR" if clear else "BLOCKED",
            blockers=tuple(blockers),
            next_pilot_blocked=not clear,
            allowed_decisions=("scale", "hold", "revise", "stop") if clear else ("revise", "stop"),
            audit_ids=tuple(audit_ids),
            transaction_signatures=tuple(signatures),
            grade_count=len(grades),
            performance={key: performance[key] for key in performance if key in {*(f"{name}_complete" for name in metric_names), "max_drawdown_usd"}},
            cumulative_loss_usd=str(cumulative_loss) if cumulative_loss is not None else "unknown",
        )

    @classmethod
    def record_operator_decision(
        cls,
        review_id: str,
        decision: str,
        rationale: str,
        authorization_id: str,
        *,
        allowed_decisions: Sequence[str] = ("scale", "hold", "revise", "stop"),
        now: datetime | None = None,
    ) -> PilotOperatorDecision:
        normalized = decision.strip().lower()
        if normalized not in {"scale", "hold", "revise", "stop"} or normalized not in set(allowed_decisions):
            raise ValueError("operator decision is not allowed for this review")
        if not review_id.strip() or not rationale.strip() or not authorization_id.strip():
            raise ValueError("review, rationale, and external authorization IDs are required")
        decision_id = f"pilot_decision_{hashlib.sha256(review_id.strip().encode('utf-8')).hexdigest()[:24]}"
        return PilotOperatorDecision(
            decision_id=decision_id,
            review_id=review_id.strip(),
            decision=normalized,
            rationale=rationale.strip(),
            authorization_id=authorization_id.strip(),
            created_at=(now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        )

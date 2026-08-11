from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence


def _timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _count(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class ProofReport:
    qualified: bool
    status: str
    blockers: tuple[str, ...]
    authorization_id: str
    wallet_public_key: str
    signer_mode: str
    signer_identity_id: str
    audit_ids: tuple[str, ...]
    transaction_signatures: tuple[str, ...]
    authority_changed: bool = False
    operator_action: str = "Actual manual-live proof remains separately authorized and deferred."

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["audit_ids"] = list(self.audit_ids)
        payload["transaction_signatures"] = list(self.transaction_signatures)
        return payload


class ManualLiveProof:
    """Qualify already-recorded round-trip evidence without executing live actions."""

    @classmethod
    def qualify(
        cls,
        audits: Sequence[Mapping[str, object]],
        ledger: Mapping[str, object],
        signer_identity: Mapping[str, object],
        authorization: Mapping[str, object],
        *,
        now: datetime | None = None,
    ) -> ProofReport:
        checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        blockers: list[str] = []

        def block(value: str) -> None:
            if value not in blockers:
                blockers.append(value)

        authorization_id = str(authorization.get("authorization_id") or "").strip()
        if not authorization_id:
            block("authorization_id")
        if authorization.get("scope") != "manual-live-proof":
            block("authorization_scope")
        issued_at = _timestamp(authorization.get("issued_at"))
        expires_at = _timestamp(authorization.get("expires_at"))
        if issued_at is None or issued_at > checked_at or checked_at - issued_at > timedelta(hours=1):
            block("authorization_not_fresh")
        if expires_at is None or expires_at <= checked_at:
            block("authorization_expired")

        wallet = str(signer_identity.get("wallet_public_key") or "").strip()
        signer_mode = str(signer_identity.get("signer_mode") or "").strip()
        signer_id = str(signer_identity.get("signer_identity_id") or "").strip()
        if not wallet or wallet != str(authorization.get("wallet_public_key") or "").strip():
            block("wallet_identity_mismatch")
        if not signer_mode or signer_mode != str(authorization.get("signer_mode") or "").strip():
            block("signer_mode_mismatch")
        if not signer_id or signer_id != str(authorization.get("signer_identity_id") or "").strip():
            block("signer_identity_mismatch")

        buy_audits = [audit for audit in audits if audit.get("action") == "buy"]
        sell_audits = [audit for audit in audits if audit.get("action") == "sell"]
        if len(buy_audits) != 1:
            block("buy_audit")
        if len(sell_audits) != 1:
            block("sell_audit")
        if any(audit.get("fixture_only") is not False for audit in audits) or not audits:
            block("actual_live_evidence_required")

        for audit in audits:
            if str(audit.get("wallet_public_key") or "") != wallet:
                block("wallet_identity_mismatch")
            if str(audit.get("signer_mode") or "") != signer_mode:
                block("signer_mode_mismatch")
            if str(audit.get("signer_identity_id") or "") != signer_id:
                block("signer_identity_mismatch")
            if audit.get("status") != "confirmed":
                block("unconfirmed_transaction")
            if not str(audit.get("transaction_signature") or "").strip():
                block("confirmed_signature")
            if str(audit.get("error") or "").strip():
                block("audit_error")
            if audit.get("reconciled") is not True:
                block("reconciliation_incomplete")
            if audit.get("fees_complete") is not True:
                block("fees_incomplete")

        for action, selected in (("buy", buy_audits), ("sell", sell_audits)):
            if len(selected) != 1:
                continue
            try:
                amount = Decimal(str(selected[0].get("amount_usd")))
            except (InvalidOperation, TypeError, ValueError):
                amount = Decimal("-1")
            if amount < Decimal("2") or amount > Decimal("5"):
                block(f"{action}_notional_bounds")

        if str(ledger.get("wallet_public_key") or "") != wallet:
            block("wallet_identity_mismatch")
        if ledger.get("round_trip_complete") is not True or _count(ledger.get("open_positions")) != 0:
            block("round_trip_incomplete")
        if ledger.get("fees_complete") is not True:
            block("fees_incomplete")
        if ledger.get("pnl_complete") is not True or ledger.get("realized_pnl_sol") is None:
            block("pnl_incomplete")
        if _count(ledger.get("unknown_transactions")) != 0:
            block("unknown_transaction")
        if ledger.get("manual_database_repair") is True:
            block("manual_database_repair")
        if _count(ledger.get("review_debt")) != 0:
            block("review_debt")

        fixture_only = "actual_live_evidence_required" in blockers
        qualified = not blockers
        return ProofReport(
            qualified=qualified,
            status="QUALIFIED" if qualified else ("DEFERRED" if fixture_only else "INVALID"),
            blockers=tuple(blockers),
            authorization_id=authorization_id,
            wallet_public_key=wallet,
            signer_mode=signer_mode,
            signer_identity_id=signer_id,
            audit_ids=tuple(str(audit.get("audit_id") or "") for audit in audits if audit.get("audit_id")),
            transaction_signatures=tuple(str(audit.get("transaction_signature") or "") for audit in audits if audit.get("transaction_signature")),
            operator_action=(
                "Review and export the qualified proof; this report grants no authority."
                if qualified
                else "Actual manual-live proof remains separately authorized and deferred."
            ),
        )

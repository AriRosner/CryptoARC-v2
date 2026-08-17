from __future__ import annotations

import json
import urllib.request
from collections.abc import Mapping
from typing import Any


class ExpoPushGateway:
    """Minimal, fail-closed boundary for the Expo Push Service."""

    SEND_URL = "https://exp.host/--/api/v2/push/send"
    RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"

    def __init__(
        self,
        *,
        enabled: bool,
        url: str = SEND_URL,
        timeout_seconds: float = 10,
    ) -> None:
        self.enabled = bool(enabled)
        self.url = str(url).strip()
        if self.url != self.SEND_URL:
            raise ValueError("Expo push delivery requires the official Expo push endpoint")
        self.timeout_seconds = max(1.0, min(30.0, float(timeout_seconds)))

    def send(
        self,
        token: str,
        payload: Mapping[str, object],
    ) -> dict[str, str]:
        if not self.enabled or not self.url:
            raise RuntimeError("Expo push delivery unavailable")
        body = {"to": token, **dict(payload)}
        try:
            request = urllib.request.Request(
                self.url,
                data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read()
            decoded: Any = json.loads(response_body.decode("utf-8"))
            tickets = decoded.get("data") if isinstance(decoded, dict) else None
            if isinstance(tickets, dict):
                ticket = tickets
            elif isinstance(tickets, list) and len(tickets) == 1:
                ticket = tickets[0]
            else:
                raise ValueError("invalid ticket response")
            ticket_id = ticket.get("id") if isinstance(ticket, dict) else None
            details = ticket.get("details") if isinstance(ticket, dict) else None
            provider_error = details.get("error") if isinstance(details, dict) else None
            if ticket.get("status") == "error" and provider_error == "DeviceNotRegistered":
                return {"status": "invalidated"}
            if ticket.get("status") == "error":
                return {"status": "rejected"}
            if (
                not isinstance(ticket, dict)
                or ticket.get("status") != "ok"
                or not isinstance(ticket_id, str)
                or not ticket_id.strip()
            ):
                raise ValueError("unsuccessful ticket")
        except Exception as exc:
            if isinstance(exc, RuntimeError) and str(exc) == "Expo push delivery unavailable":
                raise
            raise RuntimeError("Expo push delivery failed") from None
        return {"status": "sent", "ticket_id": ticket_id.strip()}

    def fetch_receipts(self, ticket_ids: list[str]) -> dict[str, object]:
        if not self.enabled or not self.url:
            raise RuntimeError("Expo push delivery unavailable")
        ids = [str(ticket_id).strip() for ticket_id in ticket_ids if str(ticket_id).strip()]
        if not ids:
            return {}
        if len(ids) > 1000:
            raise ValueError("Expo receipt batch exceeds limit")
        try:
            request = urllib.request.Request(
                self.RECEIPTS_URL,
                data=json.dumps({"ids": ids}, separators=(",", ":")).encode("utf-8"),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read()
            decoded: Any = json.loads(response_body.decode("utf-8"))
            receipts = decoded.get("data") if isinstance(decoded, dict) else None
            if not isinstance(receipts, dict):
                raise ValueError("invalid receipt response")
        except Exception as exc:
            if isinstance(exc, RuntimeError) and str(exc) == "Expo push delivery unavailable":
                raise
            raise RuntimeError("Expo push receipt lookup failed") from None
        return {
            ticket_id: receipt
            for ticket_id, receipt in receipts.items()
            if ticket_id in ids and isinstance(receipt, dict)
        }

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable


TelegramSender = Callable[[str, str, str], tuple[bool, str]]


def _telegram_send(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8", errors="replace")
    return True, body


@dataclass(slots=True)
class AlertRouter:
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_enabled: bool = False
    min_interval_seconds: int = 60
    sender: TelegramSender = _telegram_send
    sent_at: dict[str, float] = field(default_factory=dict)
    last_result: dict[str, object] = field(default_factory=lambda: {"status": "not_sent", "reason": "not run"})

    def status(self) -> dict[str, object]:
        return {
            "telegram_enabled": self.telegram_enabled,
            "telegram_configured": bool(self.telegram_bot_token and self.telegram_chat_id),
            "min_interval_seconds": self.min_interval_seconds,
            "last_result": self.last_result,
            "routes": ["telegram"],
            "critical_events": [
                "kill_switch",
                "autonomy_blocked",
                "unresolved_recovery_debt",
                "recovery_complete",
                "source_degradation",
                "failed_quote",
            ],
        }

    def test(self) -> dict[str, object]:
        return self.send("test", "CryptoARC test alert: Telegram route is connected.", force=True)

    def send(self, key: str, message: str, force: bool = False) -> dict[str, object]:
        safe_message = self._safe_message(message)
        if not self.telegram_enabled:
            return self._record("skipped", "telegram alerts disabled", key)
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return self._record("skipped", "telegram token/chat id not configured", key)
        now = time.time()
        if not force and now - self.sent_at.get(key, 0.0) < max(1, self.min_interval_seconds):
            return self._record("throttled", "alert recently sent", key)
        try:
            ok, detail = self.sender(self.telegram_bot_token, self.telegram_chat_id, safe_message)
        except Exception:
            return self._record("error", "Telegram alert delivery failed.", key)
        self.sent_at[key] = now
        return self._record("sent" if ok else "error", self._safe_message(detail)[:500], key)

    def alert_event(self, level: str, subsystem: str, message: str, operator_action: str = "") -> dict[str, object]:
        category = self._category(level, subsystem, message, operator_action)
        if not category:
            return self._record("ignored", "event is not alertable", "")
        return self.send(category, f"CryptoARC {category.replace('_', ' ')}\n{self._safe_message(message)}")

    def _category(self, level: str, subsystem: str, message: str, operator_action: str) -> str:
        text = f"{level} {subsystem} {message} {operator_action}".lower()
        if "kill switch" in text:
            return "kill_switch"
        if "autonomous" in text and ("blocked" in text or "failed" in text):
            return "autonomy_blocked"
        if "recovery debt" in text or "unresolved live audit" in text:
            return "unresolved_recovery_debt"
        if "reconciled" in text or "recovery complete" in text:
            return "recovery_complete"
        if "source" in text and any(term in text for term in ("degraded", "offline", "stale", "failed")):
            return "source_degradation"
        if "quote blocked" in text or "quote failed" in text:
            return "failed_quote"
        return ""

    def _record(self, status: str, reason: str, key: str) -> dict[str, object]:
        self.last_result = {"status": status, "reason": self._safe_message(reason), "key": key, "at": time.time()}
        return self.last_result

    def _safe_message(self, value: object) -> str:
        text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
        redactions = [
            self.telegram_bot_token,
            "seed phrase",
            "private key",
            "authorization",
            "bearer ",
        ]
        safe = text
        for item in redactions:
            if item:
                safe = safe.replace(item, "[redacted]")
        return safe[:3500]

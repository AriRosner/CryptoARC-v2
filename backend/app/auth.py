from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(slots=True)
class AuthManager:
    password: str = ""
    totp_secret: str = ""
    sessions: dict[str, float] = field(default_factory=dict)
    failed_attempts: int = 0
    locked_until: float = 0.0
    session_ttl_seconds: int = 8 * 60 * 60

    @property
    def enabled(self) -> bool:
        return bool(self.password)

    @property
    def totp_enabled(self) -> bool:
        return bool(self.totp_secret)

    def login(self, password: str, code: str = "") -> str | None:
        if self.locked_until and time.time() < self.locked_until:
            return None
        if not self.enabled:
            token = self.issue()
            return token
        if not hmac.compare_digest(password, self.password):
            self.record_failure()
            return None
        if self.totp_enabled and not verify_totp(self.totp_secret, code):
            self.record_failure()
            return None
        self.failed_attempts = 0
        return self.issue()

    def issue(self) -> str:
        token = uuid4().hex + uuid4().hex
        self.sessions[token] = time.time() + self.session_ttl_seconds
        return token

    def valid(self, token: str | None) -> bool:
        if not self.enabled:
            return True
        if not token or token not in self.sessions:
            return False
        if self.sessions[token] < time.time():
            self.sessions.pop(token, None)
            return False
        return True

    def record_failure(self) -> None:
        self.failed_attempts += 1
        if self.failed_attempts >= 5:
            self.locked_until = time.time() + 60

    def set_password(self, password: str) -> None:
        self.password = password
        self.sessions.clear()
        self.failed_attempts = 0

    def set_totp_secret(self, secret: str) -> None:
        self.totp_secret = secret
        self.sessions.clear()

    def disable_totp(self) -> None:
        self.totp_secret = ""
        self.sessions.clear()

    def rehearsal_status(self) -> dict[str, object]:
        """Describe machine-checkable auth state without exporting credentials."""
        return {
            "password_configured": self.enabled,
            "totp_configured": self.totp_enabled,
            "bearer_only": True,
            "active_sessions": len([expiry for expiry in self.sessions.values() if expiry >= time.time()]),
            "password_restart": "deferred",
            "totp_restart": "deferred",
            "authority_changed": False,
        }


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    if not code:
        return False
    normalized = code.replace(" ", "")
    for offset in range(-window, window + 1):
        if hmac.compare_digest(totp(secret, offset), normalized):
            return True
    return False


def totp(secret: str, offset: int = 0) -> str:
    key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    counter = int(time.time() // 30) + offset
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    o = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[o : o + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def random_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")

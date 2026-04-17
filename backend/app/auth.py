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
    sessions: set[str] = field(default_factory=set)

    @property
    def enabled(self) -> bool:
        return bool(self.password)

    @property
    def totp_enabled(self) -> bool:
        return bool(self.totp_secret)

    def login(self, password: str, code: str = "") -> str | None:
        if not self.enabled:
            token = self.issue()
            return token
        if not hmac.compare_digest(password, self.password):
            return None
        if self.totp_enabled and not verify_totp(self.totp_secret, code):
            return None
        return self.issue()

    def issue(self) -> str:
        token = uuid4().hex + uuid4().hex
        self.sessions.add(token)
        return token

    def valid(self, token: str | None) -> bool:
        return not self.enabled or bool(token and token in self.sessions)


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

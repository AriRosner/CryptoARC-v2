from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class SolanaReadOnlyClient:
    """Small JSON-RPC client for wallet/status checks only."""

    def __init__(self, rpc_url: str, timeout_seconds: float = 8.0) -> None:
        self.rpc_url = rpc_url.strip()
        self.timeout_seconds = timeout_seconds

    def rpc(self, method: str, params: list[Any] | None = None) -> dict[str, Any]:
        if not self.rpc_url:
            raise ValueError("Solana RPC URL is not configured")
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode("utf-8")
        request = urllib.request.Request(
            self.rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"RPC request failed: {exc}") from exc
        if "error" in body:
            message = body["error"].get("message", "unknown RPC error") if isinstance(body["error"], dict) else str(body["error"])
            raise RuntimeError(message)
        return body

    def health(self) -> str:
        result = self.rpc("getHealth").get("result")
        return str(result or "unknown")

    def balance_sol(self, wallet_address: str) -> float | None:
        wallet_address = wallet_address.strip()
        if not wallet_address:
            return None
        result = self.rpc("getBalance", [wallet_address]).get("result") or {}
        lamports = result.get("value")
        if lamports is None:
            return None
        return round(float(lamports) / 1_000_000_000, 9)

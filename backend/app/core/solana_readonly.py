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
            raise RuntimeError("RPC request failed") from exc
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

    def latest_blockhash(self) -> str:
        result = self.rpc("getLatestBlockhash", [{"commitment": "confirmed"}]).get("result") or {}
        value = result.get("value") or {}
        return str(value.get("blockhash") or "")

    def token_accounts(self, wallet_address: str) -> list[dict[str, Any]]:
        wallet_address = wallet_address.strip()
        if not wallet_address:
            return []
        accounts: list[dict[str, Any]] = []
        for program_id in (
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        ):
            result = self.rpc(
                "getTokenAccountsByOwner",
                [
                    wallet_address,
                    {"programId": program_id},
                    {"encoding": "jsonParsed"},
                ],
            ).get("result") or {}
            for item in result.get("value", []):
                account = item.get("account", {}) or {}
                info = account.get("data", {}).get("parsed", {}).get("info", {})
                token_amount = info.get("tokenAmount", {}) or {}
                amount_raw = str(token_amount.get("amount") or "0")
                ui_amount = token_amount.get("uiAmount")
                lamports = int(account.get("lamports") or 0)
                accounts.append(
                    {
                        "token_account": str(item.get("pubkey") or ""),
                        "mint": str(info.get("mint") or ""),
                        "owner": str(info.get("owner") or wallet_address),
                        "program_id": program_id,
                        "token_amount": float(ui_amount if ui_amount is not None else 0.0),
                        "token_amount_raw": amount_raw,
                        "decimals": int(token_amount.get("decimals") or 0),
                        "lamports": lamports,
                        "rent_sol": round(lamports / 1_000_000_000, 9),
                    }
                )
        return accounts

    def token_balance(self, wallet_address: str, mint: str) -> float | None:
        wallet_address = wallet_address.strip()
        mint = mint.strip()
        if not wallet_address or not mint:
            return None
        result = self.rpc(
            "getTokenAccountsByOwner",
            [
                wallet_address,
                {"mint": mint},
                {"encoding": "jsonParsed"},
            ],
        ).get("result") or {}
        total = 0.0
        for account in result.get("value", []):
            info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            amount = info.get("tokenAmount", {}).get("uiAmount")
            if amount is not None:
                total += float(amount)
        return round(total, 9)

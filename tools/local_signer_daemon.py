from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from solders.keypair import Keypair
from solders.message import to_bytes_versioned
from solders.transaction import VersionedTransaction

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.solana_readonly import SolanaReadOnlyClient  # noqa: E402


LOCALHOSTS = {"127.0.0.1", "localhost"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_keypair(value: str) -> Keypair:
    clean = value.strip()
    if not clean:
        raise ValueError("private key is required")
    if clean.startswith("["):
        parsed = json.loads(clean)
        if not isinstance(parsed, list):
            raise ValueError("private key array is invalid")
        return Keypair.from_bytes(bytes(int(item) for item in parsed))
    if "," in clean and all(part.strip().isdigit() for part in clean.split(",")):
        return Keypair.from_bytes(bytes(int(part.strip()) for part in clean.split(",")))
    try:
        return Keypair.from_base58_string(clean)
    except Exception as exc:
        raise ValueError("private key must be a base58 secret key or byte array") from exc


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "")
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class SignerDaemonConfig:
    host: str = "127.0.0.1"
    port: int = 8799
    auth_token: str = ""
    keypair: Keypair | None = None
    rpc_url: str = "https://api.mainnet-beta.solana.com"
    allow_submit: bool = False
    max_trade_sol: float = 0.001
    version: str = "v1"

    def __post_init__(self) -> None:
        if self.host not in LOCALHOSTS:
            raise ValueError("local signer daemon must bind localhost-only")
        if int(self.port) <= 0:
            raise ValueError("port must be greater than zero")
        if float(self.max_trade_sol) <= 0:
            raise ValueError("max_trade_sol must be greater than zero")


class ExecuteRequest(BaseModel):
    unsigned_transaction_base64: str = ""
    rpc_url: str = ""
    mint: str = ""
    action: str = ""
    amount: str = ""
    amount_sol: float | None = None


def config_from_env() -> SignerDaemonConfig:
    private_key = os.environ.get("CRYPTOARC_SIGNER_PRIVATE_KEY", "")
    keypair = load_keypair(private_key) if private_key.strip() else None
    return SignerDaemonConfig(
        host=os.environ.get("CRYPTOARC_SIGNER_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=int(os.environ.get("CRYPTOARC_SIGNER_PORT", "8799") or "8799"),
        auth_token=os.environ.get("CRYPTOARC_SIGNER_AUTH_TOKEN", "").strip(),
        keypair=keypair,
        rpc_url=os.environ.get("CRYPTOARC_SIGNER_RPC_URL", "https://api.mainnet-beta.solana.com").strip()
        or "https://api.mainnet-beta.solana.com",
        allow_submit=env_bool("CRYPTOARC_SIGNER_ALLOW_SUBMIT", False),
        max_trade_sol=float(os.environ.get("CRYPTOARC_SIGNER_MAX_TRADE_SOL", "0.001") or "0.001"),
    )


def create_app(config: SignerDaemonConfig) -> FastAPI:
    app = FastAPI(title="CryptoARC Local Signer Daemon", version=config.version)

    def require_auth(authorization: str = Header(default="")) -> None:
        if config.auth_token and authorization != f"Bearer {config.auth_token}":
            raise HTTPException(status_code=401, detail="signer daemon auth required")

    def policy() -> dict[str, Any]:
        return {
            "allow_submit": bool(config.allow_submit),
            "max_trade_sol": float(config.max_trade_sol),
            "rpc_url": config.rpc_url,
            "simulate_before_submit": True,
            "localhost_only": True,
        }

    @app.get("/health")
    def health(_: None = Depends(require_auth)) -> dict[str, Any]:
        has_key = config.keypair is not None
        return {
            "mode": "local_signer_daemon",
            "connected": has_key,
            "healthy": has_key,
            "wallet_public_key": str(config.keypair.pubkey()) if config.keypair else "",
            "can_sign": has_key,
            "can_unattended_sign": has_key,
            "supports_auto_buy": has_key,
            "supports_auto_sell": has_key,
            "disabled_reason": "" if has_key else "CRYPTOARC_SIGNER_PRIVATE_KEY is not configured.",
            "message": "Local signer daemon is ready." if has_key else "Local signer daemon is running without a key.",
            "transport": "localhost_http",
            "version": config.version,
            "last_heartbeat_at": utc_now_iso(),
            "policy": policy(),
        }

    @app.post("/execute")
    def execute(payload: ExecuteRequest, _: None = Depends(require_auth)) -> dict[str, Any]:
        if not payload.unsigned_transaction_base64.strip():
            raise HTTPException(status_code=400, detail="unsigned_transaction_base64 is required")
        if config.keypair is None:
            raise HTTPException(status_code=409, detail="signer key is not configured")
        if not config.allow_submit:
            raise HTTPException(status_code=403, detail="signer daemon submission is disabled")
        if payload.amount_sol is not None and float(payload.amount_sol) > float(config.max_trade_sol):
            raise HTTPException(status_code=403, detail="amount exceeds signer daemon max_trade_sol policy")

        signed = sign_transaction(config.keypair, payload.unsigned_transaction_base64)
        client = SolanaReadOnlyClient(payload.rpc_url.strip() or config.rpc_url)
        simulation = simulate_transaction(client, signed["signed_transaction_base64"])
        if not simulation.get("ok"):
            raise HTTPException(status_code=409, detail={"message": "simulation failed", "simulation": simulation})
        signature = client.rpc(
            "sendTransaction",
            [
                signed["signed_transaction_base64"],
                {
                    "encoding": "base64",
                    "skipPreflight": False,
                    "preflightCommitment": "confirmed",
                    "maxRetries": 3,
                },
            ],
        ).get("result")
        return {
            **signed,
            "signature": str(signature or signed["transaction_signature"]),
            "simulation": simulation,
            "policy": policy(),
            "submitted_at": utc_now_iso(),
        }

    return app


def sign_transaction(keypair: Keypair, unsigned_transaction_base64: str) -> dict[str, str]:
    raw = base64.b64decode(unsigned_transaction_base64.encode("utf-8"))
    transaction = VersionedTransaction.from_bytes(raw)
    signature = keypair.sign_message(to_bytes_versioned(transaction.message))
    signed = VersionedTransaction.populate(transaction.message, [signature])
    return {
        "transaction_signature": str(signature),
        "signed_transaction_base64": base64.b64encode(bytes(signed)).decode("utf-8"),
    }


def simulate_transaction(client: SolanaReadOnlyClient, signed_transaction_base64: str) -> dict[str, Any]:
    try:
        result = client.rpc(
            "simulateTransaction",
            [
                signed_transaction_base64,
                {
                    "encoding": "base64",
                    "sigVerify": False,
                    "commitment": "processed",
                },
            ],
        ).get("result") or {}
        value = result.get("value") or {}
        err = value.get("err")
        return {
            "ok": err in (None, False),
            "warning": "" if err in (None, False) else "RPC simulation reported an error.",
            "error": "" if err in (None, False) else json.dumps(err),
            "result": value,
        }
    except Exception as exc:
        return {
            "ok": False,
            "warning": "",
            "error": f"{exc.__class__.__name__}: {exc}",
            "result": {},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the CryptoARC localhost signer daemon.")
    parser.add_argument("--host", default=os.environ.get("CRYPTOARC_SIGNER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CRYPTOARC_SIGNER_PORT", "8799") or "8799"))
    args = parser.parse_args()

    os.environ["CRYPTOARC_SIGNER_HOST"] = args.host
    os.environ["CRYPTOARC_SIGNER_PORT"] = str(args.port)
    config = config_from_env()
    import uvicorn

    uvicorn.run(create_app(config), host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()

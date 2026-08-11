from __future__ import annotations

import argparse
import base64
import json
import math
import os
import sys
import threading
from dataclasses import dataclass, field
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
MIN_AUTH_TOKEN_LENGTH = 32
RPC_HEALTH_TIMEOUT_SECONDS = 1.0


@dataclass
class RpcHealthProbe:
    done: threading.Event = field(default_factory=threading.Event)
    response: object | None = None
    failed: bool = False
    expired: bool = False


_RPC_HEALTH_PROBES_LOCK = threading.Lock()
_RPC_HEALTH_PROBES: dict[str, RpcHealthProbe] = {}


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
        if not math.isfinite(float(self.max_trade_sol)) or float(self.max_trade_sol) <= 0:
            raise ValueError("max_trade_sol must be finite and greater than zero")
        if (self.keypair is not None or self.allow_submit) and len(self.auth_token.strip()) < MIN_AUTH_TOKEN_LENGTH:
            raise ValueError(f"auth_token must be at least {MIN_AUTH_TOKEN_LENGTH} characters when a key or submit mode is configured")


class ExecuteRequest(BaseModel):
    unsigned_transaction_base64: str = ""
    rpc_url: str = ""
    mint: str = ""
    action: str = ""
    amount: str = ""
    amount_sol: object | None = None


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
        ready_to_submit, disabled_reason = submission_readiness(config)
        return {
            "mode": "local_signer_daemon",
            "connected": has_key,
            "healthy": ready_to_submit,
            "wallet_public_key": str(config.keypair.pubkey()) if config.keypair else "",
            "can_sign": ready_to_submit,
            "can_unattended_sign": ready_to_submit,
            "supports_auto_buy": ready_to_submit,
            "supports_auto_sell": ready_to_submit,
            "ready_to_submit": ready_to_submit,
            "disabled_reason": disabled_reason,
            "message": "Local signer daemon is ready to submit." if ready_to_submit else "Local signer daemon is running but not ready to submit.",
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
        request_rpc_url = payload.rpc_url.strip()
        if request_rpc_url and request_rpc_url != config.rpc_url:
            raise HTTPException(status_code=400, detail="rpc_url must match the signer daemon configured RPC URL")
        if not config.allow_submit:
            raise HTTPException(status_code=403, detail="signer daemon submission is disabled")
        if isinstance(payload.amount_sol, bool):
            raise HTTPException(status_code=400, detail="amount_sol must be finite and greater than zero")
        try:
            amount_sol = float(payload.amount_sol)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="amount_sol must be finite and greater than zero") from exc
        if not math.isfinite(amount_sol) or amount_sol <= 0:
            raise HTTPException(status_code=400, detail="amount_sol must be finite and greater than zero")
        if amount_sol > float(config.max_trade_sol):
            raise HTTPException(status_code=403, detail="amount exceeds signer daemon max_trade_sol policy")

        signed = sign_transaction(config.keypair, payload.unsigned_transaction_base64)
        client = SolanaReadOnlyClient(config.rpc_url)
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


def submission_readiness(config: SignerDaemonConfig) -> tuple[bool, str]:
    if config.keypair is None:
        return False, "CRYPTOARC_SIGNER_PRIVATE_KEY is not configured."
    if not config.allow_submit:
        return False, "Signer daemon submission is disabled."
    if len(config.auth_token.strip()) < MIN_AUTH_TOKEN_LENGTH:
        return False, "Signer daemon auth is not configured."
    probe = get_or_start_rpc_health_probe(config.rpc_url)
    with _RPC_HEALTH_PROBES_LOCK:
        if probe.expired:
            return False, "Configured Solana RPC health probe timed out."
    if not probe.done.wait(RPC_HEALTH_TIMEOUT_SECONDS):
        with _RPC_HEALTH_PROBES_LOCK:
            probe.expired = True
            if probe.done.is_set() and _RPC_HEALTH_PROBES.get(config.rpc_url) is probe:
                _RPC_HEALTH_PROBES.pop(config.rpc_url, None)
        return False, "Configured Solana RPC health probe timed out."
    with _RPC_HEALTH_PROBES_LOCK:
        if probe.expired:
            if _RPC_HEALTH_PROBES.get(config.rpc_url) is probe:
                _RPC_HEALTH_PROBES.pop(config.rpc_url, None)
            return False, "Configured Solana RPC health probe timed out."
        if _RPC_HEALTH_PROBES.get(config.rpc_url) is probe:
            _RPC_HEALTH_PROBES.pop(config.rpc_url, None)
    if probe.failed:
        return False, "Configured Solana RPC health probe failed."
    response = probe.response
    if not isinstance(response, dict) or response.get("result") != "ok":
        return False, "Configured Solana RPC health probe returned a malformed response."
    return True, ""


def get_or_start_rpc_health_probe(rpc_url: str) -> RpcHealthProbe:
    with _RPC_HEALTH_PROBES_LOCK:
        probe = _RPC_HEALTH_PROBES.get(rpc_url)
        if probe is not None:
            if not probe.expired or not probe.done.is_set():
                return probe
            _RPC_HEALTH_PROBES.pop(rpc_url, None)
        probe = RpcHealthProbe()
        _RPC_HEALTH_PROBES[rpc_url] = probe
        threading.Thread(
            target=run_rpc_health_probe,
            args=(rpc_url, probe),
            name="signer-rpc-health",
            daemon=True,
        ).start()
        return probe


def run_rpc_health_probe(rpc_url: str, probe: RpcHealthProbe) -> None:
    try:
        probe.response = SolanaReadOnlyClient(
            rpc_url,
            timeout_seconds=RPC_HEALTH_TIMEOUT_SECONDS,
        ).rpc("getHealth", [])
    except Exception:
        probe.failed = True
    finally:
        probe.done.set()
        with _RPC_HEALTH_PROBES_LOCK:
            if probe.expired and _RPC_HEALTH_PROBES.get(rpc_url) is probe:
                _RPC_HEALTH_PROBES.pop(rpc_url, None)


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
        response = client.rpc(
            "simulateTransaction",
            [
                signed_transaction_base64,
                {
                    "encoding": "base64",
                    "sigVerify": False,
                    "commitment": "processed",
                },
            ],
        )
        if not isinstance(response, dict):
            return malformed_simulation_response("response must be an object")
        if "result" not in response:
            return malformed_simulation_response("missing result")
        result = response["result"]
        if not isinstance(result, dict):
            return malformed_simulation_response("result must be an object")
        if "value" not in result:
            return malformed_simulation_response("missing result.value")
        value = result["value"]
        if not isinstance(value, dict):
            return malformed_simulation_response("result.value must be an object")
        if "err" not in value:
            return malformed_simulation_response("missing result.value.err")
        err = value["err"]
        return {
            "ok": err is None,
            "warning": "" if err is None else "RPC simulation reported an error.",
            "error": "" if err is None else json.dumps(err),
            "result": value,
        }
    except Exception:
        return {
            "ok": False,
            "warning": "",
            "error": "RPC simulation failed.",
            "result": {},
        }


def malformed_simulation_response(detail: str) -> dict[str, Any]:
    return {
        "ok": False,
        "warning": "RPC simulation response was malformed.",
        "error": f"malformed RPC simulation response: {detail}",
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

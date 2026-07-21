from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_bytes
from typing import Any

from solders.keypair import Keypair
from solders.hash import Hash
from solders.message import to_bytes_versioned
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction

from app.core.solana_readonly import SolanaReadOnlyClient


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HotWalletVault:
    VERSION = 1
    ITERATIONS = 390_000

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._keypair: Keypair | None = None
        self._last_unlock_at = ""

    def status(self) -> dict[str, Any]:
        payload = self._load_payload()
        return {
            "imported": payload is not None,
            "unlocked": self._keypair is not None,
            "wallet_public_key": str(payload.get("wallet_public_key") or "") if payload else "",
            "label": str(payload.get("label") or "") if payload else "",
            "imported_at": str(payload.get("imported_at") or "") if payload else "",
            "last_unlock_at": self._last_unlock_at,
            "version": int(payload.get("version") or self.VERSION) if payload else self.VERSION,
            "storage_scope": "local_encrypted_sidecar",
            "recovery_note": "Hot wallet sidecar is local-only and is not embedded in database backup artifacts.",
        }

    def import_private_key(self, private_key: str, password: str, label: str = "") -> dict[str, Any]:
        keypair = self._parse_private_key(private_key)
        private_key_bytes = list(bytes(keypair))
        encrypted = self._encrypt(
            json.dumps(
                {
                    "private_key_bytes": private_key_bytes,
                    "wallet_public_key": str(keypair.pubkey()),
                },
                separators=(",", ":"),
            ).encode("utf-8"),
            password,
        )
        payload = {
            "version": self.VERSION,
            "wallet_public_key": str(keypair.pubkey()),
            "label": label.strip(),
            "imported_at": utc_now_iso(),
            **encrypted,
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._keypair = keypair
        self._last_unlock_at = utc_now_iso()
        return self.status()

    def unlock(self, password: str) -> dict[str, Any]:
        payload = self._require_payload()
        decrypted = self._decrypt(payload, password)
        data = json.loads(decrypted.decode("utf-8"))
        key_bytes = bytes(data["private_key_bytes"])
        self._keypair = Keypair.from_bytes(key_bytes)
        self._last_unlock_at = utc_now_iso()
        return self.status()

    def lock(self) -> dict[str, Any]:
        self._keypair = None
        return self.status()

    def clear(self) -> dict[str, Any]:
        self._keypair = None
        self._last_unlock_at = ""
        if self.path.exists():
            self.path.unlink()
        return self.status()

    def can_sign(self) -> bool:
        return self._keypair is not None

    def wallet_public_key(self) -> str:
        payload = self._load_payload()
        if payload:
            return str(payload.get("wallet_public_key") or "")
        return str(self._keypair.pubkey()) if self._keypair else ""

    def sign_transaction(self, unsigned_transaction_base64: str) -> dict[str, Any]:
        keypair = self._require_unlocked_keypair()
        raw = base64.b64decode(unsigned_transaction_base64.encode("utf-8"))
        transaction = VersionedTransaction.from_bytes(raw)
        signature = keypair.sign_message(to_bytes_versioned(transaction.message))
        signed = VersionedTransaction.populate(transaction.message, [signature])
        return {
            "transaction_signature": str(signature),
            "signed_transaction_base64": base64.b64encode(bytes(signed)).decode("utf-8"),
        }

    def simulate_and_submit(self, unsigned_transaction_base64: str, rpc_url: str) -> dict[str, Any]:
        signing = self.sign_transaction(unsigned_transaction_base64)
        client = SolanaReadOnlyClient(rpc_url)
        signed_transaction_base64 = str(signing["signed_transaction_base64"])
        simulation = self._simulate(client, signed_transaction_base64)
        if simulation.get("ok") is not True:
            detail = str(simulation.get("error") or simulation.get("warning") or "simulation failed")
            raise ValueError(f"transaction simulation failed: {detail}")
        signature = client.rpc(
            "sendTransaction",
            [
                signed_transaction_base64,
                {
                    "encoding": "base64",
                    "skipPreflight": False,
                    "preflightCommitment": "confirmed",
                    "maxRetries": 3,
                },
            ],
        ).get("result")
        return {
            **signing,
            "signature": str(signature or signing["transaction_signature"]),
            "simulation": simulation,
        }

    def transfer_sol(self, destination: str, amount_sol: float, rpc_url: str) -> dict[str, Any]:
        keypair = self._require_unlocked_keypair()
        destination_pubkey = Pubkey.from_string(destination.strip())
        lamports = int(round(float(amount_sol) * 1_000_000_000))
        if lamports <= 0:
            raise ValueError("transfer amount must be greater than zero")
        client = SolanaReadOnlyClient(rpc_url)
        blockhash_payload = client.rpc("getLatestBlockhash", [{"commitment": "confirmed"}]).get("result") or {}
        value = blockhash_payload.get("value") or {}
        blockhash = Hash.from_string(str(value.get("blockhash") or ""))
        instruction = transfer(
            TransferParams(
                from_pubkey=keypair.pubkey(),
                to_pubkey=destination_pubkey,
                lamports=lamports,
            )
        )
        message = MessageV0.try_compile(keypair.pubkey(), [instruction], [], blockhash)
        signed = VersionedTransaction(message, [keypair])
        signed_transaction_base64 = base64.b64encode(bytes(signed)).decode("utf-8")
        simulation = self._simulate(client, signed_transaction_base64)
        if not simulation.get("ok"):
            detail = str(simulation.get("error") or simulation.get("warning") or "simulation failed")
            raise ValueError(f"SOL transfer simulation failed: {detail}")
        signature = client.rpc(
            "sendTransaction",
            [
                signed_transaction_base64,
                {
                    "encoding": "base64",
                    "skipPreflight": False,
                    "preflightCommitment": "confirmed",
                    "maxRetries": 3,
                },
            ],
        ).get("result")
        return {
            "transaction_signature": str(signed.signatures[0]),
            "signed_transaction_base64": signed_transaction_base64,
            "signature": str(signature or signed.signatures[0]),
            "simulation": simulation,
            "destination": destination.strip(),
            "amount_sol": round(float(amount_sol), 9),
            "lamports": lamports,
        }

    def _simulate(self, client: SolanaReadOnlyClient, signed_transaction_base64: str) -> dict[str, Any]:
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
                return self._malformed_simulation_response("response must be an object")
            if "result" not in response:
                return self._malformed_simulation_response("missing result")
            result = response["result"]
            if not isinstance(result, dict):
                return self._malformed_simulation_response("result must be an object")
            if "value" not in result:
                return self._malformed_simulation_response("missing result.value")
            value = result["value"]
            if not isinstance(value, dict):
                return self._malformed_simulation_response("result.value must be an object")
            if "err" not in value:
                return self._malformed_simulation_response("missing result.value.err")
            err = value["err"]
            return {
                "ok": err is None,
                "warning": "" if err is None else "RPC simulation reported an error.",
                "error": "" if err is None else json.dumps(err),
                "result": value,
            }
        except Exception as exc:
            return {
                "ok": False,
                "warning": "",
                "error": f"{exc.__class__.__name__}: {exc}",
                "result": {},
            }

    @staticmethod
    def _malformed_simulation_response(detail: str) -> dict[str, Any]:
        return {
            "ok": False,
            "warning": "RPC simulation response was malformed.",
            "error": f"malformed RPC simulation response: {detail}",
            "result": {},
        }

    def _require_unlocked_keypair(self) -> Keypair:
        if self._keypair is None:
            raise ValueError("hot wallet is locked")
        return self._keypair

    def _load_payload(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _require_payload(self) -> dict[str, Any]:
        payload = self._load_payload()
        if payload is None:
            raise ValueError("no hot wallet is imported")
        return payload

    def _parse_private_key(self, private_key: str) -> Keypair:
        value = private_key.strip()
        if not value:
            raise ValueError("private key is required")
        if value.startswith("["):
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError("private key array is invalid")
            return Keypair.from_bytes(bytes(int(item) for item in parsed))
        if "," in value and all(part.strip().isdigit() for part in value.split(",")):
            return Keypair.from_bytes(bytes(int(part.strip()) for part in value.split(",")))
        try:
            return Keypair.from_base58_string(value)
        except Exception as exc:
            raise ValueError("private key must be a base58 secret key or byte array") from exc

    def _encrypt(self, plaintext: bytes, password: str) -> dict[str, str | int]:
        if not password:
            raise ValueError("password is required")
        salt = token_bytes(16)
        nonce = token_bytes(16)
        enc_key, mac_key = self._derive_keys(password, salt)
        ciphertext = self._xor_stream(plaintext, enc_key, nonce)
        mac = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
        return {
            "kdf": "pbkdf2_sha256",
            "iterations": self.ITERATIONS,
            "salt_b64": base64.b64encode(salt).decode("utf-8"),
            "nonce_b64": base64.b64encode(nonce).decode("utf-8"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("utf-8"),
            "mac_b64": base64.b64encode(mac).decode("utf-8"),
        }

    def _decrypt(self, payload: dict[str, Any], password: str) -> bytes:
        salt = base64.b64decode(str(payload["salt_b64"]).encode("utf-8"))
        nonce = base64.b64decode(str(payload["nonce_b64"]).encode("utf-8"))
        ciphertext = base64.b64decode(str(payload["ciphertext_b64"]).encode("utf-8"))
        mac = base64.b64decode(str(payload["mac_b64"]).encode("utf-8"))
        enc_key, mac_key = self._derive_keys(password, salt)
        expected = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("hot wallet password is invalid")
        return self._xor_stream(ciphertext, enc_key, nonce)

    def _derive_keys(self, password: str, salt: bytes) -> tuple[bytes, bytes]:
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, self.ITERATIONS, dklen=64)
        return derived[:32], derived[32:]

    def _xor_stream(self, payload: bytes, key: bytes, nonce: bytes) -> bytes:
        output = bytearray(len(payload))
        offset = 0
        counter = 0
        while offset < len(payload):
            block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
            chunk = payload[offset : offset + len(block)]
            for index, value in enumerate(chunk):
                output[offset + index] = value ^ block[index]
            offset += len(chunk)
            counter += 1
        return bytes(output)

import base64
import os
import unittest

from fastapi.testclient import TestClient
from solders.keypair import Keypair

from tools.local_signer_daemon import SignerDaemonConfig, create_app, load_keypair


class LocalSignerDaemonTests(unittest.TestCase):
    def test_health_requires_bearer_auth_when_token_is_configured(self) -> None:
        keypair = Keypair()
        app = create_app(
            SignerDaemonConfig(
                auth_token="secret-token",
                keypair=keypair,
                allow_submit=False,
                max_trade_sol=0.001,
            )
        )
        client = TestClient(app)

        unauthenticated = client.get("/health")
        wrong = client.get("/health", headers={"Authorization": "Bearer wrong-token"})
        ok = client.get("/health", headers={"Authorization": "Bearer secret-token"})

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(ok.status_code, 200)
        payload = ok.json()
        self.assertEqual(payload["mode"], "local_signer_daemon")
        self.assertTrue(payload["connected"])
        self.assertTrue(payload["healthy"])
        self.assertTrue(payload["can_sign"])
        self.assertTrue(payload["can_unattended_sign"])
        self.assertTrue(payload["supports_auto_buy"])
        self.assertTrue(payload["supports_auto_sell"])
        self.assertEqual(payload["wallet_public_key"], str(keypair.pubkey()))
        self.assertEqual(payload["transport"], "localhost_http")
        self.assertFalse(payload["policy"]["allow_submit"])
        self.assertEqual(payload["policy"]["max_trade_sol"], 0.001)

    def test_config_rejects_non_localhost_bind_host(self) -> None:
        with self.assertRaisesRegex(ValueError, "localhost-only"):
            SignerDaemonConfig(host="0.0.0.0")

    def test_execute_rejects_missing_transaction_before_signing(self) -> None:
        app = create_app(SignerDaemonConfig(auth_token="", keypair=Keypair()))
        client = TestClient(app)

        response = client.post("/execute", json={"action": "buy", "mint": "Mint111"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("unsigned_transaction_base64 is required", response.json()["detail"])

    def test_execute_rejects_when_submission_is_disabled(self) -> None:
        app = create_app(
            SignerDaemonConfig(
                auth_token="secret-token",
                keypair=Keypair(),
                allow_submit=False,
            )
        )
        client = TestClient(app)

        response = client.post(
            "/execute",
            json={
                "action": "buy",
                "mint": "Mint111",
                "rpc_url": "https://api.mainnet-beta.solana.com",
                "unsigned_transaction_base64": base64.b64encode(b"not-a-transaction").decode("ascii"),
            },
            headers={"Authorization": "Bearer secret-token"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("submission is disabled", response.json()["detail"])

    def test_load_keypair_accepts_json_byte_array_from_environment_value(self) -> None:
        keypair = Keypair()

        loaded = load_keypair(str(list(bytes(keypair))))

        self.assertEqual(str(loaded.pubkey()), str(keypair.pubkey()))


if __name__ == "__main__":
    unittest.main()

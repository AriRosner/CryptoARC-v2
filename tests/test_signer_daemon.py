import base64
import json
import math
import os
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from solders.keypair import Keypair

import tools.local_signer_daemon as signer_daemon
from tools.local_signer_daemon import SignerDaemonConfig, create_app, load_keypair, simulate_transaction, submission_readiness

AUTH_TOKEN = "s" * 32


class LocalSignerDaemonTests(unittest.TestCase):
    def test_expired_probe_is_discarded_before_fresh_probe_can_authorize(self) -> None:
        release_old_probe = threading.Event()
        old_probe_started = threading.Event()
        constructed_clients: list[str] = []

        class SequencedRpcClient:
            def __init__(self, rpc_url: str, timeout_seconds: float) -> None:
                constructed_clients.append(rpc_url)
                self.sequence = len(constructed_clients)

            def rpc(self, method: str, params: list[object]) -> object:
                if self.sequence == 1:
                    old_probe_started.set()
                    release_old_probe.wait(1.0)
                return {"result": "ok"}

        config = SignerDaemonConfig(
            auth_token=AUTH_TOKEN,
            keypair=Keypair(),
            rpc_url="https://expiring-rpc.invalid/private-token",
            allow_submit=True,
        )
        with signer_daemon._RPC_HEALTH_PROBES_LOCK:
            signer_daemon._RPC_HEALTH_PROBES.pop(config.rpc_url, None)
        try:
            with (
                patch("tools.local_signer_daemon.RPC_HEALTH_TIMEOUT_SECONDS", 0.05),
                patch("tools.local_signer_daemon.SolanaReadOnlyClient", SequencedRpcClient),
            ):
                first = submission_readiness(config)
                self.assertTrue(old_probe_started.is_set())

                repeated_started = time.perf_counter()
                repeated = submission_readiness(config)
                repeated_elapsed = time.perf_counter() - repeated_started

                self.assertEqual(first, (False, "Configured Solana RPC health probe timed out."))
                self.assertEqual(repeated, first)
                self.assertLess(repeated_elapsed, 0.04)
                self.assertEqual(constructed_clients, [config.rpc_url])

                release_old_probe.set()
                cleanup_deadline = time.perf_counter() + 0.5
                while time.perf_counter() < cleanup_deadline:
                    with signer_daemon._RPC_HEALTH_PROBES_LOCK:
                        if config.rpc_url not in signer_daemon._RPC_HEALTH_PROBES:
                            break
                    time.sleep(0.005)

                fresh = submission_readiness(config)

            self.assertEqual(fresh, (True, ""))
            self.assertEqual(constructed_clients, [config.rpc_url, config.rpc_url])
            with signer_daemon._RPC_HEALTH_PROBES_LOCK:
                self.assertNotIn(config.rpc_url, signer_daemon._RPC_HEALTH_PROBES)
        finally:
            release_old_probe.set()
            with signer_daemon._RPC_HEALTH_PROBES_LOCK:
                signer_daemon._RPC_HEALTH_PROBES.pop(config.rpc_url, None)

    def test_submission_readiness_is_wall_clock_bounded_and_single_flight(self) -> None:
        blocker = threading.Event()
        constructed_clients: list[str] = []

        class BlockingRpcClient:
            def __init__(self, rpc_url: str, timeout_seconds: float) -> None:
                constructed_clients.append(rpc_url)

            def rpc(self, method: str, params: list[object]) -> object:
                blocker.wait(1.0)
                return {"result": "ok"}

        config = SignerDaemonConfig(
            auth_token=AUTH_TOKEN,
            keypair=Keypair(),
            rpc_url="https://stuck-rpc.invalid/private-token",
            allow_submit=True,
        )
        try:
            with (
                patch("tools.local_signer_daemon.RPC_HEALTH_TIMEOUT_SECONDS", 0.03),
                patch("tools.local_signer_daemon.SolanaReadOnlyClient", BlockingRpcClient),
            ):
                started = time.perf_counter()
                first = submission_readiness(config)
                second = submission_readiness(config)
                elapsed = time.perf_counter() - started
        finally:
            blocker.set()

        self.assertLess(elapsed, 0.25)
        self.assertEqual(constructed_clients, [config.rpc_url])
        self.assertEqual(first, (False, "Configured Solana RPC health probe timed out."))
        self.assertEqual(second, first)
        self.assertNotIn("private-token", first[1])

    def test_health_is_not_ready_when_submit_mode_is_disabled(self) -> None:
        client = TestClient(
            create_app(
                SignerDaemonConfig(
                    auth_token=AUTH_TOKEN,
                    keypair=Keypair(),
                    allow_submit=False,
                )
            )
        )

        response = client.get("/health", headers={"Authorization": f"Bearer {AUTH_TOKEN}"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ready_to_submit"])
        self.assertFalse(payload["healthy"])
        self.assertFalse(payload["can_sign"])
        self.assertFalse(payload["can_unattended_sign"])
        self.assertFalse(payload["supports_auto_buy"])
        self.assertFalse(payload["supports_auto_sell"])
        self.assertIn("submission is disabled", payload["disabled_reason"].lower())

    def test_health_is_not_ready_for_failed_or_malformed_rpc_probe(self) -> None:
        class FailedRpcClient:
            def __init__(self, rpc_url: str, timeout_seconds: float) -> None:
                self.rpc_url = rpc_url
                self.timeout_seconds = timeout_seconds

            def rpc(self, method: str, params: list[object]) -> object:
                raise TimeoutError("secret-rpc-token-must-not-leak")

        class MalformedRpcClient(FailedRpcClient):
            def rpc(self, method: str, params: list[object]) -> object:
                return {"result": {"unexpected": "shape"}}

        for rpc_client in (FailedRpcClient, MalformedRpcClient):
            with self.subTest(rpc_client=rpc_client.__name__):
                app = create_app(
                    SignerDaemonConfig(
                        auth_token=AUTH_TOKEN,
                        keypair=Keypair(),
                        rpc_url="https://configured-rpc.invalid/private-token",
                        allow_submit=True,
                    )
                )
                with patch("tools.local_signer_daemon.SolanaReadOnlyClient", rpc_client):
                    response = TestClient(app).get(
                        "/health",
                        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
                    )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertFalse(payload["ready_to_submit"])
                self.assertFalse(payload["healthy"])
                self.assertFalse(payload["can_sign"])
                self.assertNotIn("secret-rpc-token", payload["disabled_reason"])
                self.assertNotIn("private-token", payload["disabled_reason"])

    def test_health_is_ready_only_after_bounded_successful_rpc_probe(self) -> None:
        calls: list[tuple[str, float, str, list[object]]] = []

        class HealthyRpcClient:
            def __init__(self, rpc_url: str, timeout_seconds: float) -> None:
                self.rpc_url = rpc_url
                self.timeout_seconds = timeout_seconds

            def rpc(self, method: str, params: list[object]) -> object:
                calls.append((self.rpc_url, self.timeout_seconds, method, params))
                return {"jsonrpc": "2.0", "id": 1, "result": "ok"}

        rpc_url = "https://configured-rpc.invalid"
        app = create_app(
            SignerDaemonConfig(
                auth_token=AUTH_TOKEN,
                keypair=Keypair(),
                rpc_url=rpc_url,
                allow_submit=True,
            )
        )
        with patch("tools.local_signer_daemon.SolanaReadOnlyClient", HealthyRpcClient):
            response = TestClient(app).get(
                "/health",
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ready_to_submit"])
        self.assertTrue(payload["healthy"])
        self.assertTrue(payload["can_sign"])
        self.assertTrue(payload["can_unattended_sign"])
        self.assertTrue(payload["supports_auto_buy"])
        self.assertTrue(payload["supports_auto_sell"])
        self.assertEqual(calls, [(rpc_url, calls[0][1], "getHealth", [])])
        self.assertGreater(calls[0][1], 0)
        self.assertLessEqual(calls[0][1], 2.0)

    def test_simulation_parser_requires_complete_explicit_success_shape(self) -> None:
        class StaticSimulationRpc:
            def __init__(self, response: object) -> None:
                self.response = response

            def rpc(self, method: str, params: list[object]) -> object:
                if method != "simulateTransaction":
                    raise AssertionError(f"unexpected RPC method: {method}")
                return self.response

        for response, expected_error in (
            ({}, "missing result"),
            ({"result": {}}, "missing result.value"),
            ({"result": {"value": {}}}, "missing result.value.err"),
            ({"result": {"value": []}}, "result.value must be an object"),
        ):
            with self.subTest(response=response):
                simulation = simulate_transaction(StaticSimulationRpc(response), "signed")
                self.assertFalse(simulation["ok"])
                self.assertIn(expected_error, simulation["error"])

        successful = simulate_transaction(
            StaticSimulationRpc({"result": {"value": {"err": None}}}),
            "signed",
        )
        self.assertTrue(successful["ok"])
        self.assertEqual(successful["error"], "")

    def test_config_requires_strong_auth_for_key_or_submit_mode(self) -> None:
        unsafe_configs = (
            {"keypair": Keypair()},
            {"keypair": Keypair(), "auth_token": "too-short"},
            {"allow_submit": True},
        )

        for config in unsafe_configs:
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, "auth_token must be at least 32 characters"):
                    SignerDaemonConfig(**config)

    def test_keyless_health_mode_remains_unauthenticated(self) -> None:
        with patch("tools.local_signer_daemon.SolanaReadOnlyClient", side_effect=AssertionError("keyless health must not probe RPC")):
            response = TestClient(create_app(SignerDaemonConfig())).get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["healthy"])
        self.assertFalse(response.json()["ready_to_submit"])

    def test_health_requires_bearer_auth_when_token_is_configured(self) -> None:
        keypair = Keypair()
        app = create_app(
            SignerDaemonConfig(
                auth_token=AUTH_TOKEN,
                keypair=keypair,
                allow_submit=False,
                max_trade_sol=0.001,
            )
        )
        client = TestClient(app)

        unauthenticated = client.get("/health")
        wrong = client.get("/health", headers={"Authorization": "Bearer wrong-token"})
        ok = client.get("/health", headers={"Authorization": f"Bearer {AUTH_TOKEN}"})

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(ok.status_code, 200)
        payload = ok.json()
        self.assertEqual(payload["mode"], "local_signer_daemon")
        self.assertTrue(payload["connected"])
        self.assertFalse(payload["ready_to_submit"])
        self.assertFalse(payload["healthy"])
        self.assertFalse(payload["can_sign"])
        self.assertFalse(payload["can_unattended_sign"])
        self.assertFalse(payload["supports_auto_buy"])
        self.assertFalse(payload["supports_auto_sell"])
        self.assertEqual(payload["wallet_public_key"], str(keypair.pubkey()))
        self.assertEqual(payload["transport"], "localhost_http")
        self.assertFalse(payload["policy"]["allow_submit"])
        self.assertEqual(payload["policy"]["max_trade_sol"], 0.001)

    def test_config_rejects_non_localhost_bind_host(self) -> None:
        with self.assertRaisesRegex(ValueError, "localhost-only"):
            SignerDaemonConfig(host="0.0.0.0")

    def test_config_requires_finite_positive_max_trade_sol(self) -> None:
        for value in (math.nan, math.inf, -math.inf, 0.0, -0.001):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "max_trade_sol must be finite and greater than zero"):
                    SignerDaemonConfig(max_trade_sol=value)

    def test_execute_rejects_missing_transaction_before_signing(self) -> None:
        app = create_app(SignerDaemonConfig(auth_token=AUTH_TOKEN, keypair=Keypair()))
        client = TestClient(app)

        response = client.post(
            "/execute",
            json={"action": "buy", "mint": "Mint111"},
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("unsigned_transaction_base64 is required", response.json()["detail"])

    def test_execute_rejects_when_submission_is_disabled(self) -> None:
        app = create_app(
            SignerDaemonConfig(
                auth_token=AUTH_TOKEN,
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
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("submission is disabled", response.json()["detail"])

    def test_execute_requires_finite_positive_amount_sol(self) -> None:
        client = TestClient(create_app(SignerDaemonConfig(auth_token=AUTH_TOKEN, keypair=Keypair(), allow_submit=True)))
        base_payload = {
            "action": "buy",
            "mint": "Mint111",
            "unsigned_transaction_base64": base64.b64encode(b"not-a-transaction").decode("ascii"),
        }

        for amount_sol, expected_status in (
            (None, 400),
            (0.0, 400),
            (-0.001, 400),
            (math.nan, 400),
            (math.inf, 400),
            ("not-a-number", 400),
            (True, 400),
            (False, 400),
        ):
            payload = dict(base_payload)
            if amount_sol is not None:
                payload["amount_sol"] = amount_sol
            with self.subTest(amount_sol=amount_sol):
                response = client.post(
                    "/execute",
                    content=json.dumps(payload),
                    headers={"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"},
                )
                self.assertEqual(response.status_code, expected_status)

    def test_execute_rejects_conflicting_request_rpc_url(self) -> None:
        client = TestClient(
            create_app(
                SignerDaemonConfig(
                    auth_token=AUTH_TOKEN,
                    keypair=Keypair(),
                    rpc_url="https://configured-rpc.invalid",
                )
            )
        )

        response = client.post(
            "/execute",
            json={
                "amount_sol": 0.001,
                "rpc_url": "https://request-rpc.invalid",
                "unsigned_transaction_base64": base64.b64encode(b"not-a-transaction").decode("ascii"),
            },
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rpc_url must match", response.json()["detail"])

    def test_execute_constructs_client_with_configured_rpc_only(self) -> None:
        configured_rpc_url = "https://configured-rpc.invalid"
        constructed_urls: list[str] = []
        rpc_methods: list[str] = []

        class FakeRpcClient:
            def __init__(self, rpc_url: str) -> None:
                constructed_urls.append(rpc_url)

            def rpc(self, method: str, params: list[object]) -> dict[str, object]:
                rpc_methods.append(method)
                if method != "simulateTransaction":
                    raise AssertionError("test must not reach submission")
                return {"result": {"value": {"err": {"InstructionError": [0, "blocked"]}}}}

        client = TestClient(
            create_app(
                SignerDaemonConfig(
                    auth_token=AUTH_TOKEN,
                    keypair=Keypair(),
                    rpc_url=configured_rpc_url,
                    allow_submit=True,
                )
            )
        )

        with (
            patch(
                "tools.local_signer_daemon.sign_transaction",
                return_value={"signed_transaction_base64": "signed", "transaction_signature": "signature"},
            ),
            patch("tools.local_signer_daemon.SolanaReadOnlyClient", FakeRpcClient),
        ):
            for request_rpc_url in (None, configured_rpc_url):
                payload = {"amount_sol": 0.001, "unsigned_transaction_base64": "unsigned"}
                if request_rpc_url is not None:
                    payload["rpc_url"] = request_rpc_url
                with self.subTest(request_rpc_url=request_rpc_url):
                    response = client.post(
                        "/execute",
                        json=payload,
                        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
                    )
                    self.assertEqual(response.status_code, 409)

        self.assertEqual(constructed_urls, [configured_rpc_url, configured_rpc_url])
        self.assertEqual(rpc_methods, ["simulateTransaction", "simulateTransaction"])

    def test_load_keypair_accepts_json_byte_array_from_environment_value(self) -> None:
        keypair = Keypair()

        loaded = load_keypair(str(list(bytes(keypair))))

        self.assertEqual(str(loaded.pubkey()), str(keypair.pubkey()))


if __name__ == "__main__":
    unittest.main()

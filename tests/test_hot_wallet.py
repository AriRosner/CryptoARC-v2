import base64
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.transaction import VersionedTransaction

from app.core.hot_wallet import HotWalletVault


class FailingSimulationRpc:
    calls: list[str] = []

    def __init__(self, rpc_url: str) -> None:
        self.rpc_url = rpc_url

    def rpc(self, method: str, params: list[object]) -> dict[str, object]:
        self.calls.append(method)
        if method == "simulateTransaction":
            return {
                "result": {
                    "value": {
                        "err": {"InstructionError": [0, "InsufficientFundsForRent"]},
                    }
                }
            }
        if method == "sendTransaction":
            raise AssertionError("failed simulations must not be submitted")
        raise AssertionError(f"unexpected RPC method: {method}")


class HotWalletVaultTests(unittest.TestCase):
    def test_shared_sidecar_mismatch_reports_actual_unlocked_signer(self) -> None:
        with TemporaryDirectory() as directory:
            path = f"{directory}/hotwallet.json"
            first_keypair = Keypair()
            second_keypair = Keypair()
            first = HotWalletVault(path)
            second = HotWalletVault(path)
            first.import_private_key(str(first_keypair), "first-password")
            second.import_private_key(str(second_keypair), "second-password")

            status = first.status()

            self.assertEqual(
                status["wallet_public_key"],
                str(first_keypair.pubkey()),
            )
            self.assertEqual(
                status["sidecar_wallet_public_key"],
                str(second_keypair.pubkey()),
            )
            self.assertTrue(status["sidecar_mismatch"])

    def test_shared_sidecar_mismatch_blocks_each_treasury_signing_boundary(
        self,
    ) -> None:
        class NoRpc:
            calls = 0

            def __init__(self, _rpc_url: str) -> None:
                NoRpc.calls += 1
                raise AssertionError("wallet mismatch must fail before RPC")

        with TemporaryDirectory() as directory:
            path = f"{directory}/hotwallet.json"
            first_keypair = Keypair()
            second_keypair = Keypair()
            first = HotWalletVault(path)
            second = HotWalletVault(path)
            first.import_private_key(str(first_keypair), "first-password")
            second.import_private_key(str(second_keypair), "second-password")
            expected_source = str(second_keypair.pubkey())

            with patch("app.core.hot_wallet.SolanaReadOnlyClient", NoRpc):
                for action in ("withdrawal", "profit_sweep"):
                    with self.subTest(action=action):
                        with self.assertRaisesRegex(
                            ValueError,
                            "unlocked signer|sidecar",
                        ):
                            first.transfer_sol(
                                expected_source,
                                0.01,
                                "http://must-not-run",
                                expected_public_key=expected_source,
                            )
                with self.subTest(action="rent_recovery"):
                    with self.assertRaisesRegex(
                        ValueError,
                        "unlocked signer|sidecar",
                    ):
                        first.simulate_and_submit(
                            base64.b64encode(b"must-not-sign").decode(),
                            "http://must-not-run",
                            expected_public_key=expected_source,
                        )

            self.assertEqual(NoRpc.calls, 0)

    def test_simulation_parser_requires_complete_explicit_success_shape(self) -> None:
        class StaticSimulationRpc:
            def __init__(self, response: object) -> None:
                self.response = response

            def rpc(self, method: str, params: list[object]) -> object:
                if method != "simulateTransaction":
                    raise AssertionError(f"unexpected RPC method: {method}")
                return self.response

        with TemporaryDirectory() as directory:
            vault = HotWalletVault(f"{directory}/hotwallet.json")
            for response, expected_error in (
                ({}, "missing result"),
                ({"result": {}}, "missing result.value"),
                ({"result": {"value": {}}}, "missing result.value.err"),
                ({"result": {"value": []}}, "result.value must be an object"),
            ):
                with self.subTest(response=response):
                    simulation = vault._simulate(StaticSimulationRpc(response), "signed")
                    self.assertFalse(simulation["ok"])
                    self.assertIn(expected_error, simulation["error"])

            successful = vault._simulate(
                StaticSimulationRpc({"result": {"value": {"err": None}}}),
                "signed",
            )
            self.assertTrue(successful["ok"])
            self.assertEqual(successful["error"], "")

    def test_simulate_and_submit_rejects_failed_simulation_without_submitting(self) -> None:
        keypair = Keypair()
        message = MessageV0.try_compile(keypair.pubkey(), [], [], Hash.default())
        unsigned_transaction_base64 = base64.b64encode(bytes(VersionedTransaction(message, [keypair]))).decode("ascii")

        with TemporaryDirectory() as directory:
            vault = HotWalletVault(f"{directory}/hotwallet.json")
            vault.import_private_key(str(keypair), "test-password")
            FailingSimulationRpc.calls = []

            with patch("app.core.hot_wallet.SolanaReadOnlyClient", FailingSimulationRpc):
                with self.assertRaisesRegex(ValueError, "InsufficientFundsForRent"):
                    vault.simulate_and_submit(
                        unsigned_transaction_base64,
                        "http://fake-rpc",
                        expected_public_key=str(keypair.pubkey()),
                    )

        self.assertEqual(FailingSimulationRpc.calls, ["simulateTransaction"])


if __name__ == "__main__":
    unittest.main()

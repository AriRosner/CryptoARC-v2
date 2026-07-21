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
            vault._keypair = keypair
            FailingSimulationRpc.calls = []

            with patch("app.core.hot_wallet.SolanaReadOnlyClient", FailingSimulationRpc):
                with self.assertRaisesRegex(ValueError, "InsufficientFundsForRent"):
                    vault.simulate_and_submit(unsigned_transaction_base64, "http://fake-rpc")

        self.assertEqual(FailingSimulationRpc.calls, ["simulateTransaction"])


if __name__ == "__main__":
    unittest.main()

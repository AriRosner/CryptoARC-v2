from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.core.alerts import AlertRouter
from app.core.hot_wallet import HotWalletVault
from app.core.state import BotState


SENSITIVE_MARKER = "sensitive-stack-detail"


class _FailingRpcClient:
    def health(self) -> str:
        raise RuntimeError(SENSITIVE_MARKER)

    def balance_sol(self, _wallet: str) -> float:
        raise RuntimeError(SENSITIVE_MARKER)

    def token_balance(self, _wallet: str, _mint: str) -> float:
        raise RuntimeError(SENSITIVE_MARKER)

    def rpc(self, _method: str, _params: list[object]) -> dict[str, object]:
        raise RuntimeError(SENSITIVE_MARKER)


class ExceptionSanitizationTests(unittest.TestCase):
    def test_state_rpc_failures_return_generic_external_errors(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "state.db"))
            with patch("app.core.state.SolanaReadOnlyClient", return_value=_FailingRpcClient()):
                responses = [
                    state.solana_status(),
                    state._wallet_sol_balance("wallet"),
                    state._wallet_token_balance("wallet", "mint"),
                    state._signature_status("signature"),
                    state._transaction_details("signature"),
                ]

        encoded = str(responses)
        self.assertNotIn(SENSITIVE_MARKER, encoded)
        self.assertTrue(all(item.get("error") for item in responses))

    def test_alert_delivery_failure_does_not_expose_sender_exception(self) -> None:
        def fail_sender(_token: str, _chat_id: str, _message: str) -> tuple[bool, str]:
            raise RuntimeError(SENSITIVE_MARKER)

        router = AlertRouter(
            telegram_bot_token="token",
            telegram_chat_id="chat",
            telegram_enabled=True,
            sender=fail_sender,
        )

        result = router.test()

        self.assertEqual(result["reason"], "Telegram alert delivery failed.")
        self.assertNotIn(SENSITIVE_MARKER, str(result))

    def test_hot_wallet_simulation_failure_does_not_expose_rpc_exception(self) -> None:
        vault = HotWalletVault("unused-for-simulation.json")

        result = vault._simulate(_FailingRpcClient(), "transaction")

        self.assertEqual(result["error"], "Transaction simulation failed.")
        self.assertNotIn(SENSITIVE_MARKER, str(result))


if __name__ == "__main__":
    unittest.main()

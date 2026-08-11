import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import main as main_app


class ApiErrorSanitizationTests(unittest.TestCase):
    def test_endpoint_does_not_expose_internal_validation_exception(self) -> None:
        secret = "private-rpc-token-and-stack-detail"
        payload = main_app.ApplyTuningSuggestionRequest(
            setting="strategy_profile",
            suggested_value="balanced",
        )

        with patch.object(
            main_app.state,
            "apply_tuning_suggestion",
            side_effect=ValueError(secret),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main_app.apply_tuning_suggestion(payload))

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(
            raised.exception.detail,
            "Tuning suggestion could not be applied.",
        )
        self.assertNotIn(secret, str(raised.exception.detail))

    def test_latency_status_does_not_expose_probe_exception_detail(self) -> None:
        secret = "private-pumpportal-query-token"
        previous_source = main_app.state.settings.launch_source
        previous_url = main_app.config.pumpportal_ws_url
        main_app.state.settings.launch_source = "pumpportal"
        main_app.config.pumpportal_ws_url = "wss://example.invalid/socket"
        try:
            with patch.object(
                main_app.websockets,
                "connect",
                side_effect=RuntimeError(secret),
            ):
                status = asyncio.run(main_app.update_latency_status())
        finally:
            main_app.state.settings.launch_source = previous_source
            main_app.config.pumpportal_ws_url = previous_url

        self.assertEqual(
            status["pumpportal_error"],
            "PumpPortal latency probe failure (RuntimeError)",
        )
        self.assertNotIn(secret, str(status))

    def test_review_endpoint_does_not_repackage_internal_exception(self) -> None:
        secret = "private-review-storage-detail"
        payload = main_app.LiveExecutionReviewPayload(status="reviewed")

        with patch.object(
            main_app.state,
            "review_live_request",
            side_effect=ValueError(f"not found: {secret}"),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main_app.review_live_request("missing", payload))

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(
            raised.exception.detail,
            "Live execution request could not be reviewed.",
        )
        self.assertNotIn(secret, str(raised.exception.detail))


if __name__ == "__main__":
    unittest.main()

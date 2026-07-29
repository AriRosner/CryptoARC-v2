import base64
import json
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.auth import AuthManager
from app.core.models import TradeEvent
from app.core.state import BotState
from app.mobile.contracts import MobileScope
from app.mobile.service import MobileCommandCenterService


class MobileNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = BotState(database_path=str(Path(self.directory.name) / "test.db"))
        self.encryption_key = base64.urlsafe_b64encode(
            b"cryptoarc-mobile-push-test-key!!"
        ).decode("ascii")

    @contextmanager
    def mobile_client(self):
        from app import main as main_app

        previous_state = main_app.state
        previous_auth = main_app.auth
        previous_key = main_app.config.mobile_push_token_encryption_key
        main_app.state = self.state
        main_app.auth = AuthManager(password="desktop-pass")
        main_app.config.mobile_push_token_encryption_key = self.encryption_key
        desktop_token = main_app.auth.login("desktop-pass")
        try:
            yield TestClient(main_app.app), {
                "Authorization": f"Bearer {desktop_token}"
            }
        finally:
            main_app.state = previous_state
            main_app.auth = previous_auth
            main_app.config.mobile_push_token_encryption_key = previous_key

    def claim_device(
        self,
        client: TestClient,
        desktop_headers: dict[str, str],
        *,
        name: str,
        scopes: list[str],
    ) -> dict[str, object]:
        pairing = client.post(
            "/api/mobile/pairing/start",
            json={
                "api_base_url": "https://node.tailnet.ts.net",
                "scopes": scopes,
            },
            headers=desktop_headers,
        ).json()
        response = client.post(
            "/api/mobile/pairing/claim",
            json={
                "pairing_id": pairing["id"],
                "code": pairing["code"],
                "device_name": name,
                "platform": "android",
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def service(self, sender=None) -> MobileCommandCenterService:
        async def no_op_broadcast() -> None:
            return None

        async def no_op_stop() -> dict[str, object]:
            return {}

        auth = SimpleNamespace(enabled=True, totp_enabled=True)
        config = SimpleNamespace(
            mobile_push_token_encryption_key=self.encryption_key,
            live_trading_enabled=False,
        )
        return MobileCommandCenterService(
            state_provider=lambda: self.state,
            config_provider=lambda: config,
            auth_provider=lambda: auth,
            require_dashboard_auth=lambda: None,
            broadcast_snapshot=no_op_broadcast,
            broadcast_mobile_cockpit=no_op_broadcast,
            stop_runtime_tasks=no_op_stop,
            push_sender=sender,
        )

    def save_alert(
        self,
        event_id: str = "evt_critical_123",
        *,
        message: str = "Wallet 9xSensitiveAddress submitted token secret",
        context: dict[str, object] | None = None,
    ) -> TradeEvent:
        event = TradeEvent(
            id=event_id,
            created_at=datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
            level="danger",
            message=message,
            subsystem="trade",
            operator_action="Review on the trusted backend",
            context=context or {"intent_id": "intent_abc123"},
        )
        self.state.storage.save_event(event)
        return event

    def test_push_payload_contains_only_minimal_routing_data(self) -> None:
        payload = self.service().build_push_payload(self.save_alert().to_dict())

        self.assertEqual(
            set(payload["data"]),
            {"event_id", "severity", "subsystem", "route"},
        )
        self.assertEqual(payload["data"]["route"], "/trade/intent_abc123")
        encoded = json.dumps(payload).lower()
        self.assertNotIn("wallet", encoded)
        self.assertNotIn("token", encoded)
        self.assertNotIn("9xsensitiveaddress", encoded)
        self.assertNotIn("secret", encoded)

    def test_push_payload_rejects_unallowlisted_routes_and_identifiers(self) -> None:
        service = self.service()
        for route in (
            "https://attacker.example",
            "/trade/../../diagnostics",
            "/wallet/9xSensitiveAddress",
            "/trade/intent id",
        ):
            with self.subTest(route=route):
                with self.assertRaises(ValueError):
                    service.build_push_payload(
                        {
                            **self.save_alert().to_dict(),
                            "route": route,
                        }
                    )

    def test_registration_rotation_and_unregister_leave_no_active_token(self) -> None:
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Rotation Pixel",
                scopes=[MobileScope.ALERTS],
            )
            headers = {"Authorization": f"Bearer {claim['token']}"}
            first = "ExponentPushToken[first-rotation-secret]"
            second = "ExponentPushToken[second-rotation-secret]"

            self.assertEqual(
                client.post(
                    "/api/mobile/notifications/register",
                    json={"token": first, "platform": "android"},
                    headers=headers,
                ).status_code,
                200,
            )
            self.assertEqual(
                client.post(
                    "/api/mobile/notifications/register",
                    json={"token": second, "platform": "android"},
                    headers=headers,
                ).status_code,
                200,
            )

            active = self.state.storage.load_mobile_push_registrations()
            all_rows = self.state.storage.load_mobile_push_registrations(
                include_revoked=True
            )
            self.assertEqual(len(active), 1)
            self.assertEqual(len(all_rows), 2)
            self.assertNotEqual(active[0]["token_ciphertext"], second)

            response = client.post(
                "/api/mobile/notifications/unregister",
                headers=headers,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"unregistered": True})
            self.assertEqual(self.state.storage.load_mobile_push_registrations(), [])

    def test_delivery_decrypts_only_at_sender_boundary_and_deduplicates_durably(
        self,
    ) -> None:
        raw_token = "ExponentPushToken[transient-send-boundary-secret]"
        sender = Mock(return_value={"status": "sent"})
        service = self.service(sender=sender)
        device = {"id": "mdev_delivery", "platform": "android"}
        service.register_push_token(
            device=device,
            token=raw_token,
            platform="android",
        )
        event = self.save_alert().to_dict()

        first = service.deliver_push_event(event)
        second = service.deliver_push_event(event)

        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["deduplicated"], 1)
        sender.assert_called_once()
        self.assertEqual(sender.call_args.args[0], raw_token)
        self.assertEqual(
            set(sender.call_args.args[1]["data"]),
            {"event_id", "severity", "subsystem", "route"},
        )
        self.assertEqual(self.state.storage.count_mobile_notification_deliveries(), 1)
        database_bytes = Path(self.state.storage.path).read_bytes()
        self.assertNotIn(raw_token.encode("utf-8"), database_bytes)
        self.assertNotIn(raw_token, json.dumps(first))
        self.assertNotIn(raw_token, json.dumps(second))

    def test_sender_exception_is_generic_and_never_reflects_plaintext(self) -> None:
        raw_token = "ExponentPushToken[exception-reflection-secret]"

        def failing_sender(token: str, payload: dict[str, object]):
            del payload
            raise RuntimeError(f"provider rejected {token}")

        service = self.service(sender=failing_sender)
        service.register_push_token(
            device={"id": "mdev_failure", "platform": "android"},
            token=raw_token,
            platform="android",
        )

        result = service.deliver_push_event(self.save_alert().to_dict())

        self.assertEqual(result["failed"], 1)
        self.assertNotIn(raw_token, json.dumps(result))
        self.assertNotIn("provider rejected", json.dumps(result))

    def test_acknowledgement_is_owner_scoped_and_idempotent(self) -> None:
        self.save_alert()
        with self.mobile_client() as (client, desktop_headers):
            first = self.claim_device(
                client,
                desktop_headers,
                name="First Pixel",
                scopes=[MobileScope.ALERTS],
            )
            second = self.claim_device(
                client,
                desktop_headers,
                name="Second Pixel",
                scopes=[MobileScope.ALERTS],
            )
            first_headers = {"Authorization": f"Bearer {first['token']}"}
            second_headers = {"Authorization": f"Bearer {second['token']}"}

            first_ack = client.post(
                "/api/mobile/alerts/evt_critical_123/acknowledge",
                headers=first_headers,
            )
            duplicate_ack = client.post(
                "/api/mobile/alerts/evt_critical_123/acknowledge",
                headers=first_headers,
            )
            first_alerts = client.get(
                "/api/mobile/alerts",
                headers=first_headers,
            ).json()
            second_alerts = client.get(
                "/api/mobile/alerts",
                headers=second_headers,
            ).json()

            self.assertEqual(first_ack.status_code, 200)
            self.assertEqual(duplicate_ack.status_code, 200)
            self.assertEqual(first_ack.json(), duplicate_ack.json())
            self.assertTrue(first_alerts["alerts"][0]["acknowledged"])
            self.assertFalse(second_alerts["alerts"][0]["acknowledged"])

    def test_diagnostics_are_bounded_freshness_aware_and_status_only(self) -> None:
        telegram_sender = Mock(side_effect=AssertionError("Telegram must not send"))
        self.state.alerts.telegram_enabled = True
        self.state.alerts.telegram_bot_token = "telegram-secret"
        self.state.alerts.telegram_chat_id = "chat-secret"
        self.state.alerts.sender = telegram_sender

        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Diagnostics Pixel",
                scopes=[MobileScope.DIAGNOSTICS, MobileScope.ALERTS],
            )
            headers = {"Authorization": f"Bearer {claim['token']}"}
            response = client.get("/api/mobile/diagnostics", headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            {check["id"] for check in payload["checks"]},
            {
                "tunnel",
                "api",
                "websocket",
                "token_scope",
                "push",
                "telegram",
                "clock_drift",
                "snapshot_age",
                "rpc",
                "signer",
            },
        )
        self.assertIn(payload["freshness"]["status"], {"fresh", "stale", "unavailable"})
        self.assertLessEqual(len(payload["checks"]), 10)
        telegram_sender.assert_not_called()
        encoded = json.dumps(payload).lower()
        self.assertNotIn("telegram-secret", encoded)
        self.assertNotIn("chat-secret", encoded)

    def test_diagnostic_export_recursively_redacts_sensitive_material(self) -> None:
        service = self.service()
        fixture = {
            "api_token": "raw-api-token",
            "nested": {
                "seed_phrase": "twelve words",
                "signature": "tx-signature",
                "raw_tx": "serialized transaction",
                "wallet_public_key": "9xSensitiveWalletAddress",
                "safe": "visible",
                "logs": ["Authorization: Bearer secret"],
                "path": r"C:\Users\Ari Rosner\private\wallet.json",
            },
        }

        default_export = service.redact_diagnostic_payload(fixture)
        explicit_export = service.redact_diagnostic_payload(
            fixture,
            include_public_identifiers=True,
        )

        encoded = json.dumps(default_export)
        for forbidden in (
            "raw-api-token",
            "twelve words",
            "tx-signature",
            "serialized transaction",
            "9xSensitiveWalletAddress",
            "Bearer secret",
            r"C:\Users",
        ):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(default_export["nested"]["safe"], "visible")
        self.assertNotIn("wallet_public_key", default_export["nested"])
        self.assertEqual(
            explicit_export["nested"]["wallet_public_key"],
            "9xSens...dress",
        )

    def test_raw_push_token_is_absent_from_alerts_diagnostics_and_export(self) -> None:
        raw_token = "ExponentPushToken[never-in-diagnostics-secret]"
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Privacy Pixel",
                scopes=[MobileScope.ALERTS, MobileScope.DIAGNOSTICS],
            )
            headers = {"Authorization": f"Bearer {claim['token']}"}
            client.post(
                "/api/mobile/notifications/register",
                json={"token": raw_token, "platform": "android"},
                headers=headers,
            )
            self.save_alert(message="A critical operator event occurred")
            responses = [
                client.get("/api/mobile/alerts", headers=headers),
                client.get("/api/mobile/diagnostics", headers=headers),
                client.get("/api/mobile/diagnostics/export", headers=headers),
            ]

        for response in responses:
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(raw_token, response.text)
            self.assertNotIn("token_ciphertext", response.text)
            self.assertNotIn("token_fingerprint", response.text)


if __name__ == "__main__":
    unittest.main()

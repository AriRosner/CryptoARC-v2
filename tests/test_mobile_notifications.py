import base64
import json
import sqlite3
import unittest
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
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

    def save_push_device(
        self,
        device_id: str,
        *,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
        revoked_at: str = "",
    ) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        device = {
            "id": device_id,
            "name": "Push test device",
            "platform": "android",
            "scopes": scopes or [MobileScope.ALERTS],
            "created_at": now.isoformat(),
            "last_seen_at": now.isoformat(),
            "expires_at": (expires_at or now + timedelta(days=1)).isoformat(),
            "revoked_at": revoked_at,
            "token_hash": f"hash-{device_id}",
        }
        self.state.storage.save_mobile_device(device)
        return device

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
        self.save_push_device("mdev_delivery")
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
        self.save_push_device("mdev_failure")
        service.register_push_token(
            device={"id": "mdev_failure", "platform": "android"},
            token=raw_token,
            platform="android",
        )

        result = service.deliver_push_event(self.save_alert().to_dict())

        self.assertEqual(result["failed"], 1)
        self.assertNotIn(raw_token, json.dumps(result))
        self.assertNotIn("provider rejected", json.dumps(result))

    def test_failed_and_negative_delivery_results_are_retryable(self) -> None:
        raw_token = "ExponentPushToken[retryable-delivery]"
        sender = Mock(
            side_effect=[
                RuntimeError("temporary provider failure"),
                False,
                {"status": "sent"},
            ]
        )
        self.save_push_device("mdev_retry")
        service = self.service(sender=sender)
        service.register_push_token(
            device={"id": "mdev_retry", "platform": "android"},
            token=raw_token,
            platform="android",
        )
        event = self.save_alert("evt_retryable_123").to_dict()

        failed = service.deliver_push_event(event)
        negative = service.deliver_push_event(event)
        sent = service.deliver_push_event(event)

        self.assertEqual((failed["failed"], failed["sent"]), (1, 0))
        self.assertEqual((negative["failed"], negative["sent"]), (1, 0))
        self.assertEqual((sent["sent"], sent["deduplicated"]), (1, 0))
        self.assertEqual(sender.call_count, 3)

    def test_delivery_claims_are_atomic_reclaimable_and_attempt_bound(self) -> None:
        storage = self.state.storage
        first_at = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
        first_attempt = storage.reserve_mobile_notification_delivery(
            delivery_id="delivery-first",
            attempt_id="attempt-first",
            event_id="evt_claim",
            device_id="mdev_claim",
            channel="critical",
            registration_id="registration-first",
            attempted_at=first_at.isoformat(),
            lease_seconds=30,
        )
        self.assertEqual(first_attempt, "attempt-first")

        contenders_at = (first_at + timedelta(seconds=31)).isoformat()
        with ThreadPoolExecutor(max_workers=8) as executor:
            attempts = list(
                executor.map(
                    lambda index: storage.reserve_mobile_notification_delivery(
                        delivery_id=f"delivery-{index}",
                        attempt_id=f"attempt-{index}",
                        event_id="evt_claim",
                        device_id="mdev_claim",
                        channel="critical",
                        registration_id="registration-first",
                        attempted_at=contenders_at,
                        lease_seconds=30,
                    ),
                    range(8),
                )
            )
        reclaimed = [attempt for attempt in attempts if attempt]
        self.assertEqual(len(reclaimed), 1)
        self.assertFalse(
            storage.finish_mobile_notification_delivery(
                attempt_id="attempt-first",
                status="sent",
                updated_at=(first_at + timedelta(seconds=32)).isoformat(),
            )
        )
        self.assertTrue(
            storage.finish_mobile_notification_delivery(
                attempt_id=reclaimed[0],
                status="failed",
                updated_at=(first_at + timedelta(seconds=33)).isoformat(),
            )
        )

    def test_delivery_revalidates_device_lifecycle_and_alert_scope(self) -> None:
        sender = Mock(return_value={"status": "sent"})
        service = self.service(sender=sender)
        now = datetime.now(timezone.utc)
        cases = {
            "expired": {
                "scopes": [MobileScope.ALERTS],
                "expires_at": now - timedelta(seconds=1),
            },
            "revoked": {
                "scopes": [MobileScope.ALERTS],
                "revoked_at": now.isoformat(),
            },
            "scope": {"scopes": [MobileScope.DIAGNOSTICS]},
            "missing": {"scopes": [MobileScope.ALERTS]},
        }
        for label, overrides in cases.items():
            device_id = f"mdev_{label}"
            self.save_push_device(device_id)
            service.register_push_token(
                device={"id": device_id, "platform": "android"},
                token=f"ExponentPushToken[{label}-lifecycle]",
                platform="android",
            )
            self.save_push_device(device_id, **overrides)
            if label == "missing":
                connection = sqlite3.connect(self.state.storage.path)
                try:
                    connection.execute("DELETE FROM mobile_devices WHERE id = ?", (device_id,))
                    connection.commit()
                finally:
                    connection.close()

        result = service.deliver_push_event(
            self.save_alert("evt_lifecycle_123").to_dict()
        )

        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["invalidated"], 4)
        sender.assert_not_called()
        self.assertEqual(self.state.storage.load_mobile_push_registrations(), [])

    def test_delivery_revalidates_authorization_after_claim_before_send(self) -> None:
        sender = Mock(return_value={"status": "sent"})
        service = self.service(sender=sender)
        self.save_push_device("mdev_claim_revoked")
        service.register_push_token(
            device={"id": "mdev_claim_revoked", "platform": "android"},
            token="ExponentPushToken[claim-revoked]",
            platform="android",
        )
        reserve = self.state.storage.reserve_mobile_notification_delivery

        def reserve_then_revoke(**kwargs):
            attempt = reserve(**kwargs)
            self.state.storage.revoke_mobile_device_and_push_registrations(
                "mdev_claim_revoked",
                datetime.now(timezone.utc).isoformat(),
            )
            return attempt

        with unittest.mock.patch.object(
            self.state.storage,
            "reserve_mobile_notification_delivery",
            side_effect=reserve_then_revoke,
        ):
            result = service.deliver_push_event(
                self.save_alert("evt_claim_revoked").to_dict()
            )

        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["invalidated"], 1)
        self.assertEqual(result["failed"], 0)
        sender.assert_not_called()

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
            first_alert = next(
                alert
                for alert in first_alerts["alerts"]
                if alert["event_id"] == "evt_critical_123"
            )
            second_alert = next(
                alert
                for alert in second_alerts["alerts"]
                if alert["event_id"] == "evt_critical_123"
            )
            self.assertTrue(first_alert["acknowledged"])
            self.assertFalse(second_alert["acknowledged"])

    def test_acknowledgement_rejects_events_outside_exact_alert_predicate(self) -> None:
        info_event = TradeEvent(
            id="evt_info_ordinary",
            created_at=datetime.now(timezone.utc),
            level="info",
            message="Routine status",
            subsystem="system",
            operator_action="",
            context={},
        )
        self.state.storage.save_event(info_event)
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Predicate Pixel",
                scopes=[MobileScope.ALERTS],
            )
            headers = {"Authorization": f"Bearer {claim['token']}"}

            response = client.post(
                "/api/mobile/alerts/evt_info_ordinary/acknowledge",
                headers=headers,
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.state.storage.load_mobile_alert_acknowledgements(
                device_id=str(claim["device"]["id"])
            ),
            [],
        )

    def test_push_registration_rejects_blank_and_malformed_tokens_generically(self) -> None:
        malformed = [
            "   ",
            "not-an-expo-token",
            "ExponentPushToken[]",
            "ExponentPushToken[malicious-secret!]",
        ]
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Validation Pixel",
                scopes=[MobileScope.ALERTS],
            )
            headers = {"Authorization": f"Bearer {claim['token']}"}
            for token in malformed:
                with self.subTest(token=token):
                    response = client.post(
                        "/api/mobile/notifications/register",
                        json={"token": token, "platform": "android"},
                        headers=headers,
                    )
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(
                        response.json(),
                        {"detail": "Invalid mobile push registration request"},
                    )
                    if token.strip():
                        self.assertNotIn(token.strip(), response.text)
        self.assertEqual(self.state.storage.load_mobile_push_registrations(), [])

    def test_restore_preview_accounts_for_notifications_and_restore_revokes_destinations(self) -> None:
        self.save_push_device("mdev_restore")
        service = self.service(sender=Mock(return_value={"status": "sent"}))
        service.register_push_token(
            device={"id": "mdev_restore", "platform": "android"},
            token="ExponentPushToken[restore-destination]",
            platform="android",
        )
        self.save_alert("evt_restore_alert")
        self.state.storage.acknowledge_mobile_alert(
            acknowledgement_id="ack_restore",
            device_id="mdev_restore",
            event_id="evt_restore_alert",
            acknowledged_at=datetime.now(timezone.utc).isoformat(),
        )
        service.deliver_push_event(
            self.save_alert("evt_restore_delivery").to_dict()
        )
        artifact = self.state.storage.create_backup_artifact()
        self.state.storage.revoke_mobile_device_and_push_registrations(
            "mdev_restore",
            datetime.now(timezone.utc).isoformat(),
        )

        preview = self.state.storage.preview_restore_artifact(artifact)
        result = self.state.storage.restore_backup_artifact(artifact)

        for table in (
            "mobile_push_registrations",
            "mobile_alert_acknowledgements",
            "mobile_notification_deliveries",
        ):
            self.assertIn(table, preview["table_deltas"])
        restored_device = self.state.storage.load_mobile_device("mdev_restore")
        self.assertTrue(restored_device["revoked_at"])
        self.assertEqual(self.state.storage.load_mobile_push_registrations(), [])
        self.assertEqual(
            self.state.storage.count_mobile_notification_deliveries(), 1
        )
        self.assertEqual(
            len(
                self.state.storage.load_mobile_alert_acknowledgements(
                    device_id="mdev_restore"
                )
            ),
            1,
        )
        self.assertTrue(result["mobile_credentials_revoked"])

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

    def test_diagnostics_do_not_invent_transport_or_snapshot_observations(self) -> None:
        device = {
            "id": "mdev_diagnostic_provenance",
            "scopes": [MobileScope.DIAGNOSTICS],
        }
        payload = self.service().diagnostics(device=device)
        checks = {check["id"]: check for check in payload["checks"]}

        self.assertEqual(payload["freshness"]["status"], "unavailable")
        for check_id in ("tunnel", "websocket", "clock_drift", "snapshot_age"):
            self.assertEqual(checks[check_id]["status"], "unavailable")
            self.assertIsNone(checks[check_id]["observed_at"])
        self.assertEqual(checks["api"]["status"], "healthy")
        self.assertIsNotNone(checks["api"]["observed_at"])

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

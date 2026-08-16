import base64
import asyncio
import json
import sqlite3
import time
import unittest
from contextlib import closing, contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from app.auth import AuthManager
from app.core.models import TradeEvent
from app.core.state import BotState
from app.mobile.contracts import MobileScope
from app.mobile.expo_push import ExpoPushGateway
from app.mobile.service import MobileCommandCenterService


class MobileNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = BotState(database_path=str(Path(self.directory.name) / "test.db"))
        self.encryption_key = base64.urlsafe_b64encode(
            b"cryptoarc-mobile-push-test-key!!"
        ).decode("ascii")

    def test_expo_gateway_posts_minimal_payload_and_returns_ticket_id(self) -> None:
        token = "ExponentPushToken[provider-boundary-secret]"
        payload = {
            "title": "Critical CryptoARC alert",
            "body": "Open CryptoARC after unlocking.",
            "channelId": "critical",
            "data": {
                "event_id": "evt_gateway_123",
                "severity": "danger",
                "subsystem": "trade",
                "route": "/trade/intent_123",
            },
        }

        class Response:
            def read(self) -> bytes:
                return b'{"data":[{"status":"ok","id":"ticket-123"}]}'

            def __enter__(self):
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        gateway = ExpoPushGateway(enabled=True, timeout_seconds=3)
        with patch(
            "app.mobile.expo_push.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            result = gateway.send(token, payload)

        self.assertEqual(result, {"status": "sent", "ticket_id": "ticket-123"})
        request = urlopen.call_args.args[0]
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 3)
        self.assertEqual(request.full_url, "https://exp.host/--/api/v2/push/send")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        encoded = json.loads(request.data.decode("utf-8"))
        self.assertEqual(encoded["to"], token)
        self.assertEqual(encoded["data"], payload["data"])
        self.assertEqual(encoded["channelId"], "critical")
        self.assertNotIn("message", encoded)

    def test_expo_gateway_normalizes_provider_rejection_without_reflection(self) -> None:
        token = "ExponentPushToken[provider-error-secret]"

        class Response:
            def read(self) -> bytes:
                return b'{"data":[{"status":"error","message":"reject provider-error-secret"}]}'

            def __enter__(self):
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        gateway = ExpoPushGateway(enabled=True)
        with patch(
            "app.mobile.expo_push.urllib.request.urlopen",
            return_value=Response(),
        ):
            result = gateway.send(
                token,
                {"title": "alert", "body": "open", "data": {}},
            )

        self.assertEqual(result, {"status": "rejected"})
        self.assertNotIn(token, json.dumps(result))
        self.assertNotIn("reject provider", json.dumps(result))

    def test_expo_gateway_rejects_non_official_send_endpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "official Expo push endpoint"):
            ExpoPushGateway(
                enabled=True,
                url="https://attacker.example/collect",
            )

    def test_expo_gateway_normalizes_ticket_level_device_invalidation(self) -> None:
        class Response:
            def read(self) -> bytes:
                return b'{"data":[{"status":"error","details":{"error":"DeviceNotRegistered"}}]}'

            def __enter__(self):
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        gateway = ExpoPushGateway(enabled=True)
        with patch(
            "app.mobile.expo_push.urllib.request.urlopen",
            return_value=Response(),
        ):
            result = gateway.send(
                "ExponentPushToken[ticket-invalidated-secret]",
                {"title": "alert", "body": "open", "data": {}},
            )

        self.assertEqual(result, {"status": "invalidated"})

    def test_expo_gateway_fetches_bounded_receipts(self) -> None:
        class Response:
            def read(self) -> bytes:
                return b'{"data":{"ticket-1":{"status":"ok"}}}'

            def __enter__(self):
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        gateway = ExpoPushGateway(enabled=True)
        with patch(
            "app.mobile.expo_push.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            receipts = gateway.fetch_receipts(["ticket-1"])

        self.assertEqual(receipts, {"ticket-1": {"status": "ok"}})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://exp.host/--/api/v2/push/getReceipts")
        self.assertEqual(json.loads(request.data.decode("utf-8")), {"ids": ["ticket-1"]})

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

    def service(self, sender=None, receipt_fetcher=None) -> MobileCommandCenterService:
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
            push_receipt_fetcher=receipt_fetcher,
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

    def test_delivery_persists_expo_ticket_for_later_receipt_reconciliation(self) -> None:
        raw_token = "ExponentPushToken[receipt-ledger-secret]"
        service = self.service(
            sender=Mock(return_value={"status": "sent", "ticket_id": "ticket-receipt-123"})
        )
        self.save_push_device("mdev_receipt")
        service.register_push_token(
            device={"id": "mdev_receipt", "platform": "android"},
            token=raw_token,
            platform="android",
        )

        result = service.deliver_push_event(self.save_alert("evt_receipt_123").to_dict())
        pending = self.state.storage.load_pending_mobile_notification_receipts(limit=10)

        self.assertEqual((result["sent"], result["failed"]), (1, 0))
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["ticket_id"], "ticket-receipt-123")
        self.assertTrue(pending[0]["registration_id"])
        self.assertNotIn(raw_token, json.dumps(pending))

    def test_existing_delivery_ledger_migrates_receipt_columns_idempotently(self) -> None:
        legacy_path = Path(self.directory.name) / "legacy-notification-ledger.db"
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.execute(
                """
                CREATE TABLE mobile_notification_deliveries (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    registration_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(event_id, device_id, channel)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO mobile_notification_deliveries (
                    id, event_id, device_id, channel, registration_id,
                    attempt_id, status, attempted_at, lease_expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "delivery-legacy",
                    "event-legacy",
                    "device-legacy",
                    "critical",
                    "registration-legacy",
                    "attempt-legacy",
                    "sent",
                    "2026-08-16T12:00:00+00:00",
                    "2026-08-16T12:01:00+00:00",
                    "2026-08-16T12:00:01+00:00",
                ),
            )
            connection.commit()

        from app.core.storage import Storage

        Storage(str(legacy_path))
        Storage(str(legacy_path))
        with closing(sqlite3.connect(legacy_path)) as connection:
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(mobile_notification_deliveries)"
                ).fetchall()
            }
            row = connection.execute(
                """
                SELECT provider_ticket_id, receipt_status, receipt_checked_at
                FROM mobile_notification_deliveries
                WHERE id = 'delivery-legacy'
                """
            ).fetchone()

        self.assertTrue(
            {"provider_ticket_id", "receipt_status", "receipt_checked_at"}.issubset(columns)
        )
        self.assertEqual(row, ("", "", None))

    def test_device_not_registered_receipt_revokes_only_its_registration(self) -> None:
        raw_token = "ExponentPushToken[receipt-invalidated-secret]"
        service = self.service(
            sender=Mock(return_value={"status": "sent", "ticket_id": "ticket-invalidated-123"}),
            receipt_fetcher=Mock(
                return_value={
                    "ticket-invalidated-123": {
                        "status": "error",
                        "details": {"error": "DeviceNotRegistered"},
                    }
                }
            ),
        )
        self.save_push_device("mdev_invalidated")
        service.register_push_token(
            device={"id": "mdev_invalidated", "platform": "android"},
            token=raw_token,
            platform="android",
        )
        service.deliver_push_event(self.save_alert("evt_invalidated_123").to_dict())

        result = service.reconcile_push_receipts()

        self.assertEqual(
            result,
            {
                "checked": 1,
                "confirmed": 0,
                "invalidated": 1,
                "failed": 0,
                "retryable": 0,
            },
        )
        self.assertEqual(self.state.storage.load_mobile_push_registrations(), [])
        self.assertEqual(self.state.storage.load_pending_mobile_notification_receipts(), [])
        self.assertNotIn(raw_token, json.dumps(result))

    def test_ticket_level_device_invalidation_revokes_without_retrying(self) -> None:
        raw_token = "ExponentPushToken[ticket-level-invalidated-secret]"
        service = self.service(sender=Mock(return_value={"status": "invalidated"}))
        self.save_push_device("mdev_ticket_invalidated")
        service.register_push_token(
            device={"id": "mdev_ticket_invalidated", "platform": "android"},
            token=raw_token,
            platform="android",
        )

        result = service.deliver_push_event(
            self.save_alert("evt_ticket_invalidated_123").to_dict()
        )

        self.assertEqual((result["invalidated"], result["failed"]), (1, 0))
        self.assertEqual(self.state.storage.load_mobile_push_registrations(), [])
        self.assertNotIn(raw_token, json.dumps(result))

    def test_ticket_level_provider_rejection_is_terminal(self) -> None:
        sender = Mock(return_value={"status": "rejected"})
        service = self.service(sender=sender)
        self.save_push_device("mdev_ticket_rejected")
        service.register_push_token(
            device={"id": "mdev_ticket_rejected", "platform": "android"},
            token="ExponentPushToken[ticket-level-rejected-secret]",
            platform="android",
        )
        event = self.save_alert("evt_ticket_rejected_123").to_dict()

        first = service.deliver_push_event(event)
        second = service.deliver_push_event(event)

        self.assertEqual((first["failed"], first["sent"]), (1, 0))
        self.assertEqual(second["deduplicated"], 1)
        sender.assert_called_once()

    def test_terminal_receipt_error_is_not_polled_forever(self) -> None:
        service = self.service(
            sender=Mock(return_value={"status": "sent", "ticket_id": "ticket-terminal-error"}),
            receipt_fetcher=Mock(
                return_value={
                    "ticket-terminal-error": {
                        "status": "error",
                        "details": {"error": "MessageTooBig"},
                    }
                }
            ),
        )
        self.save_push_device("mdev_terminal_receipt")
        service.register_push_token(
            device={"id": "mdev_terminal_receipt", "platform": "android"},
            token="ExponentPushToken[terminal-receipt-secret]",
            platform="android",
        )
        service.deliver_push_event(self.save_alert("evt_terminal_receipt").to_dict())

        result = service.reconcile_push_receipts()

        self.assertEqual(result["failed"], 1)
        self.assertEqual(self.state.storage.load_pending_mobile_notification_receipts(), [])

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

    def test_corrupt_token_ciphertext_is_invalidated_without_provider_retry(self) -> None:
        sender = Mock(return_value={"status": "sent"})
        service = self.service(sender=sender)
        self.save_push_device("mdev_corrupt_ciphertext")
        service.register_push_token(
            device={"id": "mdev_corrupt_ciphertext", "platform": "android"},
            token="ExponentPushToken[corrupt-ciphertext-secret]",
            platform="android",
        )
        with closing(sqlite3.connect(self.state.storage.path)) as connection:
            connection.execute(
                "UPDATE mobile_push_registrations SET token_ciphertext = 'not-fernet'"
            )
            connection.commit()

        result = service.deliver_push_event(
            self.save_alert("evt_corrupt_ciphertext").to_dict()
        )

        self.assertEqual((result["invalidated"], result["retryable"]), (1, 0))
        self.assertEqual(self.state.storage.load_mobile_push_registrations(), [])
        sender.assert_not_called()

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

    def test_delivery_claim_waits_for_brief_writer_contention(self) -> None:
        storage = self.state.storage
        attempted_at = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc).isoformat()

        with closing(sqlite3.connect(storage.path)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            with ThreadPoolExecutor(max_workers=1) as executor:
                claim = executor.submit(
                    storage.reserve_mobile_notification_delivery,
                    delivery_id="delivery-contended",
                    attempt_id="attempt-contended",
                    event_id="evt-contended",
                    device_id="mdev-contended",
                    channel="critical",
                    registration_id="registration-contended",
                    attempted_at=attempted_at,
                    lease_seconds=30,
                )
                time.sleep(0.25)
                writer.rollback()
                self.assertEqual(claim.result(timeout=1), "attempt-contended")

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

    def test_diagnostics_do_not_report_push_healthy_without_provider(self) -> None:
        service = self.service()
        self.save_push_device(
            "mdev_push_diagnostics",
            scopes=[MobileScope.DIAGNOSTICS, MobileScope.ALERTS],
        )
        service.register_push_token(
            device={"id": "mdev_push_diagnostics", "platform": "android"},
            token="ExponentPushToken[diagnostics-registration]",
            platform="android",
        )

        payload = service.diagnostics(
            device={
                "id": "mdev_push_diagnostics",
                "scopes": [MobileScope.DIAGNOSTICS, MobileScope.ALERTS],
            }
        )
        push = next(check for check in payload["checks"] if check["id"] == "push")

        self.assertEqual(push["status"], "unavailable")

    def test_event_dispatch_queues_only_alerts_and_is_bounded(self) -> None:
        from app import main as main_app

        async def exercise() -> None:
            previous_enabled = main_app.config.mobile_expo_push_enabled
            previous_queue = main_app.mobile_push_queue
            main_app.config.mobile_expo_push_enabled = True
            main_app.mobile_push_queue = asyncio.Queue(maxsize=1)
            try:
                info = self.save_alert("evt_dispatch_info").to_dict()
                info["level"] = "info"
                warning = self.save_alert("evt_dispatch_warning").to_dict()
                warning["level"] = "warning"
                danger = self.save_alert("evt_dispatch_danger").to_dict()
                main_app._dispatch_mobile_push_event(
                    SimpleNamespace(level="info", to_dict=lambda: info)
                )
                self.assertTrue(main_app.mobile_push_queue.empty())
                main_app._dispatch_mobile_push_event(
                    SimpleNamespace(level="warning", to_dict=lambda: warning)
                )
                main_app._dispatch_mobile_push_event(
                    SimpleNamespace(level="danger", to_dict=lambda: danger)
                )
                self.assertEqual(main_app.mobile_push_queue.qsize(), 1)
                self.assertEqual(
                    (await main_app.mobile_push_queue.get())["id"],
                    "evt_dispatch_warning",
                )
            finally:
                main_app.mobile_push_queue = previous_queue
                main_app.config.mobile_expo_push_enabled = previous_enabled

        asyncio.run(exercise())

    def test_delivery_worker_retries_transient_failures_but_not_rejections(self) -> None:
        from app import main as main_app

        async def exercise() -> None:
            with patch.object(
                main_app.mobile_service,
                "deliver_push_event",
                side_effect=[
                    {"failed": 1, "retryable": 1},
                    {"failed": 0, "retryable": 0},
                ],
            ) as deliver, patch.object(
                main_app.asyncio,
                "sleep",
                new=AsyncMock(),
            ) as sleep:
                await main_app._deliver_mobile_push_with_retry({"id": "evt_retry_worker"})
                self.assertEqual(deliver.call_count, 2)
                sleep.assert_awaited_once_with(1)

            with patch.object(
                main_app.mobile_service,
                "deliver_push_event",
                return_value={"failed": 1, "retryable": 0},
            ) as rejected:
                await main_app._deliver_mobile_push_with_retry({"id": "evt_rejected_worker"})
                rejected.assert_called_once()

        asyncio.run(exercise())

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

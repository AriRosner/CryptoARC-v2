import base64
import json
import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth import AuthManager
from app.core.state import BotState
from app.mobile.contracts import MobileActionStatus, MobileRealtimeEnvelope, MobileScope


class MobileCommandCenterContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = BotState(database_path=str(Path(self.directory.name) / "test.db"))

    def test_new_scopes_are_not_granted_by_legacy_control(self) -> None:
        pairing = self.state.create_mobile_pairing(
            api_base_url="https://node.tailnet.ts.net",
            scopes=["mobile:monitor", "mobile:control"],
        )
        claim = self.state.claim_mobile_pairing(
            pairing["id"], pairing["code"], "Pixel", "android"
        )

        self.assertNotIn(MobileScope.TRADE_EXECUTE, claim["scopes"])
        self.assertNotIn(MobileScope.TREASURY_REQUEST, claim["scopes"])

    def test_new_scopes_are_granted_only_when_explicitly_requested(self) -> None:
        pairing = self.state.create_mobile_pairing(
            api_base_url="https://node.tailnet.ts.net",
            scopes=[MobileScope.WALLET_READ, MobileScope.TRADE_EXECUTE],
        )
        claim = self.state.claim_mobile_pairing(
            pairing["id"], pairing["code"], "Pixel", "android"
        )

        self.assertIn(MobileScope.WALLET_READ, claim["scopes"])
        self.assertIn(MobileScope.TRADE_EXECUTE, claim["scopes"])
        self.assertNotIn(MobileScope.TREASURY_REQUEST, claim["scopes"])

    def test_realtime_envelope_requires_monotonic_sequence(self) -> None:
        first = MobileRealtimeEnvelope(
            event_type="cockpit",
            server_time=datetime.now(timezone.utc),
            sequence=41,
            payload={"ok": True},
        )
        second = MobileRealtimeEnvelope(
            event_type="cockpit",
            server_time=datetime.now(timezone.utc),
            sequence=42,
            payload={"ok": True},
        )

        self.assertEqual(first.sequence + 1, second.sequence)
        self.assertEqual(second.schema_version, 1)
        with self.assertRaises(ValidationError):
            MobileRealtimeEnvelope(
                event_type="cockpit",
                server_time=datetime.now(timezone.utc),
                sequence=0,
                payload={},
            )

    def test_action_status_contract_is_stable(self) -> None:
        self.assertEqual(
            [status.value for status in MobileActionStatus],
            [
                "pending",
                "verifying",
                "confirmed",
                "failed",
                "cancelled",
                "expired",
                "review_required",
            ],
        )

    def test_mobile_command_center_migration_creates_exact_tables(self) -> None:
        expected = {
            "mobile_action_receipts",
            "mobile_destination_authorizations",
            "mobile_push_registrations",
            "mobile_alert_acknowledgements",
        }
        with closing(sqlite3.connect(self.state.storage.path)) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            migration = connection.execute(
                "SELECT version FROM schema_migrations WHERE migration_id = ?",
                ("010_mobile_command_center",),
            ).fetchone()

        self.assertTrue(expected.issubset(tables))
        self.assertEqual(migration, (10,))

    def test_monitor_only_token_cannot_read_wallet_or_approve_trade(self) -> None:
        from app import main as main_app

        previous_state = main_app.state
        previous_auth = main_app.auth
        main_app.state = self.state
        main_app.auth = AuthManager(password="desktop-pass")
        desktop_token = main_app.auth.login("desktop-pass")
        try:
            client = TestClient(main_app.app)
            pairing = client.post(
                "/api/mobile/pairing/start",
                json={
                    "api_base_url": "https://node.tailnet.ts.net",
                    "scopes": [MobileScope.MONITOR],
                },
                headers={"Authorization": f"Bearer {desktop_token}"},
            ).json()
            claim = client.post(
                "/api/mobile/pairing/claim",
                json={
                    "pairing_id": pairing["id"],
                    "code": pairing["code"],
                    "device_name": "Pixel",
                    "platform": "android",
                },
            ).json()
            headers = {"Authorization": f"Bearer {claim['token']}"}

            self.assertEqual(client.get("/api/mobile/wallet", headers=headers).status_code, 403)
            self.assertEqual(
                client.post(
                    "/api/mobile/trades/intent-1/approve",
                    headers=headers,
                ).status_code,
                403,
            )
        finally:
            main_app.state = previous_state
            main_app.auth = previous_auth

    def test_push_registration_fails_closed_without_valid_encryption_key(self) -> None:
        from app import main as main_app

        previous_state = main_app.state
        previous_auth = main_app.auth
        previous_key = main_app.config.mobile_push_token_encryption_key
        main_app.state = self.state
        main_app.auth = AuthManager(password="desktop-pass")
        desktop_token = main_app.auth.login("desktop-pass")
        try:
            client = TestClient(main_app.app)
            pairing = client.post(
                "/api/mobile/pairing/start",
                json={
                    "api_base_url": "https://node.tailnet.ts.net",
                    "scopes": [MobileScope.ALERTS],
                },
                headers={"Authorization": f"Bearer {desktop_token}"},
            ).json()
            claim = client.post(
                "/api/mobile/pairing/claim",
                json={
                    "pairing_id": pairing["id"],
                    "code": pairing["code"],
                    "device_name": "Pixel",
                    "platform": "android",
                },
            ).json()
            headers = {"Authorization": f"Bearer {claim['token']}"}

            for key in ("", "not-a-valid-fernet-key"):
                with self.subTest(key=key):
                    main_app.config.mobile_push_token_encryption_key = key
                    response = client.post(
                        "/api/mobile/notifications/register",
                        json={
                            "token": "ExponentPushToken[raw-secret-token]",
                            "platform": "android",
                        },
                        headers=headers,
                    )
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(self.state.storage.count_mobile_push_registrations(), 0)
        finally:
            main_app.state = previous_state
            main_app.auth = previous_auth
            main_app.config.mobile_push_token_encryption_key = previous_key

    def test_push_registration_persists_only_ciphertext(self) -> None:
        from app import main as main_app

        previous_state = main_app.state
        previous_auth = main_app.auth
        previous_key = main_app.config.mobile_push_token_encryption_key
        main_app.state = self.state
        main_app.auth = AuthManager(password="desktop-pass")
        main_app.config.mobile_push_token_encryption_key = base64.urlsafe_b64encode(
            b"cryptoarc-mobile-push-test-key!!"
        ).decode("ascii")
        raw_token = "ExponentPushToken[raw-secret-token]"
        desktop_token = main_app.auth.login("desktop-pass")
        try:
            client = TestClient(main_app.app)
            pairing = client.post(
                "/api/mobile/pairing/start",
                json={
                    "api_base_url": "https://node.tailnet.ts.net",
                    "scopes": [MobileScope.ALERTS],
                },
                headers={"Authorization": f"Bearer {desktop_token}"},
            ).json()
            claim = client.post(
                "/api/mobile/pairing/claim",
                json={
                    "pairing_id": pairing["id"],
                    "code": pairing["code"],
                    "device_name": "Pixel",
                    "platform": "android",
                },
            ).json()

            response = client.post(
                "/api/mobile/notifications/register",
                json={"token": raw_token, "platform": "android"},
                headers={"Authorization": f"Bearer {claim['token']}"},
            )
            registrations = self.state.storage.load_mobile_push_registrations()
            encoded_response = json.dumps(response.json())
            encoded_export = json.dumps(self.state.export_data("all"))
            encoded_backup = json.dumps(self.state.storage.create_backup_artifact())
            encoded_events = json.dumps(
                [event.to_dict() for event in self.state.storage.load_all_events(100)]
            )
            database_bytes = Path(self.state.storage.path).read_bytes()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(registrations), 1)
            self.assertNotEqual(registrations[0]["token_ciphertext"], raw_token)
            self.assertNotIn(raw_token, encoded_response)
            self.assertNotIn(raw_token, encoded_export)
            self.assertNotIn(raw_token, encoded_backup)
            self.assertNotIn(raw_token, encoded_events)
            self.assertNotIn(raw_token.encode("utf-8"), database_bytes)
            self.assertNotIn("token_ciphertext", encoded_response)
            self.assertNotIn("token_fingerprint", encoded_response)
        finally:
            main_app.state = previous_state
            main_app.auth = previous_auth
            main_app.config.mobile_push_token_encryption_key = previous_key


if __name__ == "__main__":
    unittest.main()

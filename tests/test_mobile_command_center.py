import base64
import json
import sqlite3
import unittest
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth import AuthManager
from app.core.state import BotState
from app.core.storage import Storage
from app.mobile.contracts import MobileActionStatus, MobileRealtimeEnvelope, MobileScope


class MobileCommandCenterContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = BotState(database_path=str(Path(self.directory.name) / "test.db"))

    @contextmanager
    def mobile_client(self):
        from app import main as main_app

        previous_state = main_app.state
        previous_auth = main_app.auth
        previous_key = main_app.config.mobile_push_token_encryption_key
        main_app.state = self.state
        main_app.auth = AuthManager(password="desktop-pass")
        main_app.config.mobile_push_token_encryption_key = base64.urlsafe_b64encode(
            b"cryptoarc-mobile-push-test-key!!"
        ).decode("ascii")
        desktop_token = main_app.auth.login("desktop-pass")
        try:
            yield (
                TestClient(main_app.app),
                {"Authorization": f"Bearer {desktop_token}"},
            )
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
        pairing_response = client.post(
            "/api/mobile/pairing/start",
            json={
                "api_base_url": "https://node.tailnet.ts.net",
                "scopes": scopes,
            },
            headers=desktop_headers,
        )
        self.assertEqual(pairing_response.status_code, 200)
        pairing = pairing_response.json()
        claim_response = client.post(
            "/api/mobile/pairing/claim",
            json={
                "pairing_id": pairing["id"],
                "code": pairing["code"],
                "device_name": name,
                "platform": "android",
            },
        )
        self.assertEqual(claim_response.status_code, 200)
        return claim_response.json()

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

    def test_mobile_command_center_migration_contract_is_exact_and_idempotent(self) -> None:
        expected_columns = {
            "mobile_action_receipts": [
                ("id", "TEXT", 0, 1),
                ("idempotency_key_hash", "TEXT", 1, 0),
                ("device_id", "TEXT", 1, 0),
                ("action_type", "TEXT", 1, 0),
                ("entity_id", "TEXT", 1, 0),
                ("payload", "TEXT", 1, 0),
                ("status", "TEXT", 1, 0),
                ("created_at", "TEXT", 1, 0),
                ("updated_at", "TEXT", 1, 0),
            ],
            "mobile_destination_authorizations": [
                ("id", "TEXT", 0, 1),
                ("payload", "TEXT", 1, 0),
                ("created_at", "TEXT", 1, 0),
                ("expires_at", "TEXT", 1, 0),
                ("used_at", "TEXT", 0, 0),
            ],
            "mobile_push_registrations": [
                ("id", "TEXT", 0, 1),
                ("device_id", "TEXT", 1, 0),
                ("token_ciphertext", "TEXT", 1, 0),
                ("token_fingerprint", "TEXT", 1, 0),
                ("platform", "TEXT", 1, 0),
                ("created_at", "TEXT", 1, 0),
                ("updated_at", "TEXT", 1, 0),
                ("revoked_at", "TEXT", 0, 0),
            ],
            "mobile_alert_acknowledgements": [
                ("id", "TEXT", 0, 1),
                ("device_id", "TEXT", 1, 0),
                ("event_id", "TEXT", 1, 0),
                ("acknowledged_at", "TEXT", 1, 0),
            ],
        }
        expected_unique_columns = {
            "mobile_action_receipts": {("idempotency_key_hash",)},
            "mobile_destination_authorizations": set(),
            "mobile_push_registrations": {("token_fingerprint",)},
            "mobile_alert_acknowledgements": {("device_id", "event_id")},
        }
        with closing(sqlite3.connect(self.state.storage.path)) as connection:
            actual_columns = {}
            actual_unique_columns = {}
            for table in expected_columns:
                actual_columns[table] = [
                    (str(row[1]), str(row[2]), int(row[3]), int(row[5]))
                    for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
                ]
                unique_columns = set()
                for index in connection.execute(f"PRAGMA index_list({table})").fetchall():
                    if not int(index[2]) or str(index[3]) != "u":
                        continue
                    unique_columns.add(
                        tuple(
                            str(row[2])
                            for row in connection.execute(
                                f"PRAGMA index_info({index[1]})"
                            ).fetchall()
                        )
                    )
                actual_unique_columns[table] = unique_columns
            migration = connection.execute(
                "SELECT version FROM schema_migrations WHERE migration_id = ?",
                ("010_mobile_command_center",),
            ).fetchone()

        self.assertEqual(actual_columns, expected_columns)
        self.assertEqual(actual_unique_columns, expected_unique_columns)
        self.assertEqual(migration, (10,))

        Storage(str(self.state.storage.path))
        with closing(sqlite3.connect(self.state.storage.path)) as connection:
            migration_count = connection.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE migration_id = ?",
                ("010_mobile_command_center",),
            ).fetchone()
        self.assertEqual(migration_count, (1,))

    def test_restore_migrates_version_nine_artifact_forward(self) -> None:
        root = Path(self.directory.name)
        source = Storage(str(root / "version-nine.db"))
        task_tables = {
            "mobile_action_receipts",
            "mobile_destination_authorizations",
            "mobile_push_registrations",
            "mobile_alert_acknowledgements",
        }
        with closing(sqlite3.connect(source.path)) as connection:
            for table in task_tables:
                connection.execute(f"DROP TABLE {table}")
            connection.execute(
                "DELETE FROM schema_migrations WHERE migration_id = ?",
                ("010_mobile_command_center",),
            )
            connection.commit()
        artifact = source.create_backup_artifact()
        target = Storage(str(root / "restore-target.db"))

        preview = target.preview_restore_artifact(artifact)
        result = target.restore_backup_artifact(artifact)

        self.assertEqual(preview["schema_version"], 9)
        self.assertIn("Artifact will be migrated forward after restore.", preview["warnings"])
        self.assertEqual(result["status"], "restored")
        self.assertEqual(target.schema_status()["current_version"], 10)
        with closing(sqlite3.connect(target.path)) as connection:
            restored_tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        self.assertTrue(task_tables.issubset(restored_tables))

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

    def test_explicitly_scoped_wallet_and_trade_requests_stop_at_501(self) -> None:
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Scoped Pixel",
                scopes=[MobileScope.WALLET_READ, MobileScope.TRADE_EXECUTE],
            )
            headers = {"Authorization": f"Bearer {claim['token']}"}
            financial_counts_before = (
                self.state.storage.count_trades(),
                self.state.storage.count_live_execution_requests(),
                self.state.storage.count_live_sessions(),
                self.state.storage.count_live_execution_audits(),
                self.state.storage.count_live_intents(),
                self.state.storage.count_live_ledger_positions(),
                self.state.storage.count_events(),
            )

            wallet_response = client.get("/api/mobile/wallet", headers=headers)
            trade_response = client.post(
                "/api/mobile/trades/intent-1/approve",
                headers=headers,
            )

            self.assertEqual(wallet_response.status_code, 501)
            self.assertEqual(trade_response.status_code, 501)
            self.assertEqual(
                (
                    self.state.storage.count_trades(),
                    self.state.storage.count_live_execution_requests(),
                    self.state.storage.count_live_sessions(),
                    self.state.storage.count_live_execution_audits(),
                    self.state.storage.count_live_intents(),
                    self.state.storage.count_live_ledger_positions(),
                    self.state.storage.count_events(),
                ),
                financial_counts_before,
            )

    def test_invalid_push_registration_requests_never_echo_the_token(self) -> None:
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Push Pixel",
                scopes=[MobileScope.ALERTS],
            )
            headers = {"Authorization": f"Bearer {claim['token']}"}
            cases = {
                "malformed": {
                    "token": {"secret": "malformed-push-token-secret"},
                    "platform": "android",
                },
                "empty": {"token": "", "platform": "android"},
                "overlong": {
                    "token": "overlong-push-token-secret-" + ("x" * 4096),
                    "platform": "android",
                },
            }

            for name, request_body in cases.items():
                with self.subTest(name=name):
                    response = client.post(
                        "/api/mobile/notifications/register",
                        json=request_body,
                        headers=headers,
                    )
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(
                        response.json(),
                        {"detail": "Invalid mobile push registration request"},
                    )
                    self.assertNotIn("malformed-push-token-secret", response.text)
                    self.assertNotIn("overlong-push-token-secret", response.text)

            self.assertEqual(self.state.storage.count_mobile_push_registrations(), 0)

    def test_device_revocation_revokes_every_linked_push_registration(self) -> None:
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Revoked Pixel",
                scopes=[MobileScope.ALERTS],
            )
            mobile_headers = {"Authorization": f"Bearer {claim['token']}"}
            for token in (
                "ExponentPushToken[first-secret-token]",
                "ExponentPushToken[second-secret-token]",
            ):
                response = client.post(
                    "/api/mobile/notifications/register",
                    json={"token": token, "platform": "android"},
                    headers=mobile_headers,
                )
                self.assertEqual(response.status_code, 200)

            revoke_response = client.post(
                f"/api/mobile/devices/{claim['device']['id']}/revoke",
                headers=desktop_headers,
            )

            self.assertEqual(revoke_response.status_code, 200)
            self.assertEqual(self.state.storage.load_mobile_push_registrations(), [])
            registrations = self.state.storage.load_mobile_push_registrations(
                include_revoked=True
            )
            self.assertEqual(len(registrations), 2)
            self.assertTrue(all(str(item["revoked_at"] or "") for item in registrations))

    def test_same_device_duplicate_returns_canonical_persisted_metadata(self) -> None:
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Duplicate Pixel",
                scopes=[MobileScope.ALERTS],
            )
            headers = {"Authorization": f"Bearer {claim['token']}"}
            token = "ExponentPushToken[canonical-same-device-secret]"
            with patch(
                "app.mobile.service.utc_now",
                return_value=datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc),
            ):
                first = client.post(
                    "/api/mobile/notifications/register",
                    json={"token": token, "platform": "android"},
                    headers=headers,
                )
            with patch(
                "app.mobile.service.utc_now",
                return_value=datetime(2026, 7, 26, 12, 5, tzinfo=timezone.utc),
            ):
                second = client.post(
                    "/api/mobile/notifications/register",
                    json={"token": token, "platform": "android"},
                    headers=headers,
                )
            persisted = self.state.storage.load_mobile_push_registrations(
                include_revoked=True
            )

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(len(persisted), 1)
            self.assertEqual(
                second.json()["registration"]["id"],
                first.json()["registration"]["id"],
            )
            self.assertEqual(
                second.json()["registration"]["created_at"],
                first.json()["registration"]["created_at"],
            )
            self.assertEqual(second.json()["registration"]["id"], persisted[0]["id"])
            self.assertEqual(
                second.json()["registration"]["created_at"],
                persisted[0]["created_at"],
            )
            self.assertEqual(
                second.json()["registration"]["updated_at"],
                persisted[0]["updated_at"],
            )

    def test_cross_device_duplicate_reassigns_canonical_registration(self) -> None:
        with self.mobile_client() as (client, desktop_headers):
            first_claim = self.claim_device(
                client,
                desktop_headers,
                name="First Pixel",
                scopes=[MobileScope.ALERTS],
            )
            second_claim = self.claim_device(
                client,
                desktop_headers,
                name="Second Pixel",
                scopes=[MobileScope.ALERTS],
            )
            token = "ExponentPushToken[canonical-cross-device-secret]"
            first = client.post(
                "/api/mobile/notifications/register",
                json={"token": token, "platform": "android"},
                headers={"Authorization": f"Bearer {first_claim['token']}"},
            )
            second = client.post(
                "/api/mobile/notifications/register",
                json={"token": token, "platform": "android"},
                headers={"Authorization": f"Bearer {second_claim['token']}"},
            )
            persisted = self.state.storage.load_mobile_push_registrations()

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(len(persisted), 1)
            self.assertEqual(
                second.json()["registration"]["id"],
                first.json()["registration"]["id"],
            )
            self.assertEqual(
                second.json()["registration"]["created_at"],
                first.json()["registration"]["created_at"],
            )
            self.assertEqual(
                second.json()["registration"]["device_id"],
                second_claim["device"]["id"],
            )
            self.assertEqual(persisted[0]["device_id"], second_claim["device"]["id"])

            first_revoke = client.post(
                f"/api/mobile/devices/{first_claim['device']['id']}/revoke",
                headers=desktop_headers,
            )
            self.assertEqual(first_revoke.status_code, 200)
            self.assertEqual(len(self.state.storage.load_mobile_push_registrations()), 1)

            second_revoke = client.post(
                f"/api/mobile/devices/{second_claim['device']['id']}/revoke",
                headers=desktop_headers,
            )
            self.assertEqual(second_revoke.status_code, 200)
            self.assertEqual(self.state.storage.load_mobile_push_registrations(), [])

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

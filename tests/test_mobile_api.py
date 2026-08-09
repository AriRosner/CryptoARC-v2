import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth import AuthManager
from app.core.models import BotStatus
from app.core.state import BotState
from app.mobile.contracts import MobileRealtimeEnvelope, MobileScope


class MobileApiTests(unittest.TestCase):
    def make_state(self, directory: str) -> BotState:
        return BotState(database_path=str(Path(directory) / "test.db"))

    def test_mobile_realtime_contract_fixture_is_backend_valid(self) -> None:
        fixture_path = (
            Path(__file__).parents[1]
            / "mobile"
            / "src"
            / "core"
            / "__fixtures__"
            / "mobile-realtime-envelope-v1.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

        envelope = MobileRealtimeEnvelope.model_validate(fixture)

        self.assertEqual(envelope.event_type, "cockpit")
        self.assertEqual(envelope.schema_version, 1)
        self.assertEqual(envelope.sequence, 42)
        self.assertEqual(envelope.payload["artifact_type"], "cryptoarc_mobile_cockpit")

    def test_mobile_pairing_claim_revocation_and_token_hashing(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)

            pairing = state.create_mobile_pairing(
                api_base_url="https://cryptoarc-node.tailnet.ts.net",
                scopes=[MobileScope.MONITOR, MobileScope.CONTROL],
            )
            pairing_rows = state.storage.load_mobile_pairing_requests(include_claimed=True)

            self.assertEqual(pairing["api_base_url"], "https://cryptoarc-node.tailnet.ts.net")
            self.assertEqual(pairing["manual_code"], pairing["code"])
            self.assertNotIn(pairing["code"], json.dumps(pairing_rows))
            self.assertIn("code_hash", pairing_rows[0])

            claimed = state.claim_mobile_pairing(
                pairing_id=pairing["id"],
                code=pairing["code"],
                device_name="Pixel 9",
                platform="android",
            )
            device_rows = state.storage.load_mobile_devices(include_revoked=True)
            device = state.validate_mobile_token(claimed["token"], required_scope="mobile:monitor")

            self.assertEqual(claimed["device"]["name"], "Pixel 9")
            self.assertEqual(device["id"], claimed["device"]["id"])
            self.assertNotIn(MobileScope.TRADE_EXECUTE, claimed["scopes"])
            self.assertNotIn(MobileScope.TREASURY_REQUEST, claimed["scopes"])
            self.assertNotIn(claimed["token"], json.dumps(device_rows))
            self.assertIn("token_hash", device_rows[0])

            state.revoke_mobile_device(device["id"])

            self.assertIsNone(state.validate_mobile_token(claimed["token"], required_scope="mobile:monitor"))

    def test_mobile_pairing_rejects_wrong_codes_and_prevents_reuse(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            pairing = state.create_mobile_pairing(api_base_url="https://cryptoarc-node.tailnet.ts.net")

            with self.assertRaises(ValueError):
                state.claim_mobile_pairing(pairing["id"], "000000", "Pixel 9", "android")

            claimed = state.claim_mobile_pairing(pairing["id"], pairing["code"], "Pixel 9", "android")
            self.assertTrue(claimed["token"])

            with self.assertRaises(ValueError):
                state.claim_mobile_pairing(pairing["id"], pairing["code"], "Other phone", "android")

    def test_mobile_pairing_claim_is_atomic_across_independent_state_instances(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "test.db")
            creator = BotState(database_path=database_path)
            pairing = creator.create_mobile_pairing(
                api_base_url="https://cryptoarc-node.tailnet.ts.net",
                scopes=[MobileScope.MONITOR, MobileScope.CONTROL],
            )
            claimers = [BotState(database_path=database_path), BotState(database_path=database_path)]
            start_barrier = threading.Barrier(2)
            stale_read_barrier = threading.Barrier(2)

            # Force the legacy read-then-write path to expose the race deterministically.
            for claimer in claimers:
                original_load = claimer.storage.load_mobile_pairing_request

                def synchronized_load(pairing_id: str, load=original_load):
                    value = load(pairing_id)
                    stale_read_barrier.wait(timeout=5)
                    return value

                claimer.storage.load_mobile_pairing_request = synchronized_load

            def claim(index: int):
                start_barrier.wait(timeout=5)
                try:
                    return claimers[index].claim_mobile_pairing(
                        pairing["id"],
                        pairing["code"],
                        f"Pixel {index}",
                        "android",
                    )
                except ValueError as exc:
                    return exc

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(claim, range(2)))

            successes = [result for result in results if isinstance(result, dict)]
            failures = [result for result in results if isinstance(result, ValueError)]
            devices = creator.storage.load_mobile_devices(include_revoked=True)
            stored_pairing = creator.storage.load_mobile_pairing_request(pairing["id"])

            self.assertEqual(len(successes), 1)
            self.assertEqual(len(failures), 1)
            self.assertEqual(len(devices), 1)
            self.assertEqual(stored_pairing["claimed_device_id"], successes[0]["device"]["id"])
            self.assertEqual(successes[0]["scopes"], [MobileScope.MONITOR, MobileScope.CONTROL])

    def test_mobile_pairing_claim_rolls_back_when_device_insert_fails(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            pairing = state.create_mobile_pairing(
                api_base_url="https://cryptoarc-node.tailnet.ts.net",
                scopes=[MobileScope.MONITOR],
            )
            duplicate_id = "mdev_duplicate"
            state.storage.save_mobile_device({
                "id": duplicate_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": "",
                "revoked_at": "",
            })
            device = {
                "id": duplicate_id,
                "name": "Pixel 9",
                "platform": "android",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "revoked_at": "",
                "token_hash": "hash",
                "paired_from_pairing_id": pairing["id"],
            }

            with self.assertRaises(Exception):
                state.storage.claim_mobile_pairing_request(
                    pairing_id=pairing["id"],
                    presented_code_hash=state._hash_mobile_secret(pairing["code"]),
                    device=device,
                    claimed_at=datetime.now(timezone.utc).isoformat(),
                    default_max_failed_attempts=state.MOBILE_PAIRING_MAX_FAILED_ATTEMPTS,
                )

            stored = state.storage.load_mobile_pairing_request(pairing["id"])
            self.assertEqual(stored["claimed_at"], "")
            self.assertEqual(stored["claimed_device_id"], "")
            claimed = state.claim_mobile_pairing(
                pairing["id"], pairing["code"], "Replacement Pixel", "android"
            )
            self.assertEqual(claimed["device"]["name"], "Replacement Pixel")

    def test_mobile_scope_blocks_control_when_device_is_monitor_only(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            pairing = state.create_mobile_pairing(
                api_base_url="https://cryptoarc-node.tailnet.ts.net",
                scopes=["mobile:monitor"],
            )
            claimed = state.claim_mobile_pairing(pairing["id"], pairing["code"], "Pixel 9", "android")

            self.assertIsNotNone(state.validate_mobile_token(claimed["token"], required_scope="mobile:monitor"))
            self.assertIsNone(state.validate_mobile_token(claimed["token"], required_scope="mobile:control"))

    def test_mobile_cockpit_payload_is_safety_first_and_omits_secrets(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            state.add_event("warning", "Source degraded", subsystem="source", operator_action="Inspect source health.")

            payload = state.mobile_cockpit(live_trading_enabled=False, local_auth_enabled=True)
            encoded = json.dumps(payload).lower()

            self.assertEqual(payload["bot"]["status"], BotStatus.STOPPED.value)
            self.assertIn("source", payload)
            self.assertIn("readiness", payload)
            self.assertIn("live", payload)
            self.assertIn("open_risk", payload)
            self.assertIn("pnl", payload)
            self.assertIn("allowed_actions", payload)
            self.assertTrue(payload["allowed_actions"]["start"])
            self.assertTrue(payload["allowed_actions"]["kill_switch"])
            self.assertEqual(payload["alerts"]["latest"][0]["message"], "Source degraded")
            self.assertNotIn("private_key", encoded)
            self.assertNotIn("seed", encoded)
            self.assertNotIn("token_hash", encoded)

    def test_mobile_guarded_actions_record_operator_events(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)

            started = state.mobile_start_bot()
            stopped = state.mobile_stop_bot()
            killed = state.mobile_set_kill_switch(True, "leaving desk")
            messages = [event.message for event in state.storage.load_all_events(20)]

            self.assertEqual(started["bot"]["status"], BotStatus.RUNNING.value)
            self.assertEqual(stopped["bot"]["status"], BotStatus.STOPPED.value)
            self.assertTrue(killed["live"]["kill_switch_enabled"])
            self.assertTrue(any("Mobile cockpit started bot" in message for message in messages))
            self.assertTrue(any("Mobile cockpit stopped bot" in message for message in messages))
            self.assertTrue(any("Live kill switch enabled" in message for message in messages))

    def test_mobile_http_pairing_scope_and_revoke_flow(self) -> None:
        from app import main as main_app

        with TemporaryDirectory() as directory:
            previous_state = main_app.state
            previous_auth = main_app.auth
            main_app.state = self.make_state(directory)
            main_app.auth = AuthManager(password="desktop-pass")
            desktop_token = main_app.auth.login("desktop-pass")
            headers = {"Authorization": f"Bearer {desktop_token}"}

            try:
                client = TestClient(main_app.app)
                pairing_response = client.post(
                    "/api/mobile/pairing/start",
                    json={
                        "api_base_url": "https://cryptoarc-node.tailnet.ts.net",
                        "scopes": ["mobile:monitor"],
                    },
                    headers=headers,
                )
                self.assertEqual(pairing_response.status_code, 200)
                pairing = pairing_response.json()

                claim_response = client.post(
                    "/api/mobile/pairing/claim",
                    json={
                        "pairing_id": pairing["id"],
                        "code": pairing["code"],
                        "device_name": "Pixel 9",
                        "platform": "android",
                    },
                )
                self.assertEqual(claim_response.status_code, 200)
                mobile_token = claim_response.json()["token"]
                mobile_headers = {"Authorization": f"Bearer {mobile_token}"}

                cockpit_response = client.get("/api/mobile/cockpit", headers=mobile_headers)
                self.assertEqual(cockpit_response.status_code, 200)
                self.assertEqual(cockpit_response.json()["device"]["name"], "Pixel 9")

                denied_response = client.post("/api/mobile/actions/start", headers=mobile_headers)
                self.assertEqual(denied_response.status_code, 403)

                devices_response = client.get("/api/mobile/devices", headers=headers)
                self.assertEqual(devices_response.status_code, 200)
                device_id = devices_response.json()["devices"][0]["id"]

                revoke_response = client.post(f"/api/mobile/devices/{device_id}/revoke", headers=headers)
                self.assertEqual(revoke_response.status_code, 200)
                denied_after_revoke = client.get("/api/mobile/cockpit", headers=mobile_headers)
                self.assertEqual(denied_after_revoke.status_code, 401)
            finally:
                main_app.state = previous_state
                main_app.auth = previous_auth

    def test_rest_auth_rejects_query_string_tokens(self) -> None:
        from app import main as main_app

        with TemporaryDirectory() as directory:
            previous_state = main_app.state
            previous_auth = main_app.auth
            main_app.state = self.make_state(directory)
            main_app.auth = AuthManager(password="desktop-pass")
            token = main_app.auth.login("desktop-pass")

            try:
                client = TestClient(main_app.app)
                query_response = client.get(f"/api/security/status?token={token}")
                header_response = client.get("/api/security/status", headers={"Authorization": f"Bearer {token}"})

                self.assertEqual(query_response.status_code, 401)
                self.assertEqual(header_response.status_code, 200)
            finally:
                main_app.state = previous_state
                main_app.auth = previous_auth

    def test_websocket_tickets_are_scoped_hashed_single_use_and_fail_closed(self) -> None:
        from app import main as main_app

        with TemporaryDirectory() as directory:
            previous_state = main_app.state
            previous_auth = main_app.auth
            previous_monotonic = getattr(main_app.mobile_service, "_monotonic", None)
            now = [1000.0]
            main_app.state = self.make_state(directory)
            main_app.auth = AuthManager(password="desktop-pass")
            main_app.mobile_service._monotonic = lambda: now[0]

            try:
                client = TestClient(main_app.app)
                pairing = main_app.state.create_mobile_pairing(
                    api_base_url="https://cryptoarc-node.tailnet.ts.net",
                    scopes=[MobileScope.MONITOR],
                )
                claimed = main_app.state.claim_mobile_pairing(
                    pairing["id"],
                    pairing["code"],
                    "Pixel 9",
                    "android",
                )
                token = claimed["token"]
                headers = {"Authorization": f"Bearer {token}"}

                denied_query_auth = client.post(f"/api/mobile/ws-ticket?token={token}")
                self.assertEqual(denied_query_auth.status_code, 401)

                issued = client.post("/api/mobile/ws-ticket", headers=headers)
                self.assertEqual(issued.status_code, 200)
                ticket_payload = issued.json()
                ticket = ticket_payload["ticket"]
                self.assertEqual(ticket_payload["scope"], MobileScope.MONITOR)
                self.assertLessEqual(ticket_payload["ttl_seconds"], 30)
                self.assertNotEqual(ticket, token)
                self.assertNotIn(ticket, repr(main_app.mobile_service._ws_tickets))

                with client.websocket_connect(f"/ws/mobile?ticket={ticket}") as websocket:
                    first_envelope = websocket.receive_json()
                    self.assertEqual(
                        first_envelope["payload"]["device"]["id"],
                        claimed["device"]["id"],
                    )
                    self.assertEqual(first_envelope["event_type"], "cockpit")
                    self.assertEqual(first_envelope["schema_version"], 1)
                    self.assertGreaterEqual(first_envelope["sequence"], 1)

                    pairing_response = client.post(
                        "/api/mobile/pairing/start",
                        json={"api_base_url": "https://cryptoarc-node.tailnet.ts.net"},
                        headers={"Authorization": f"Bearer {main_app.auth.login('desktop-pass')}"},
                    )
                    self.assertEqual(pairing_response.status_code, 200)
                    second_envelope = websocket.receive_json()
                    self.assertEqual(second_envelope["event_type"], "cockpit")
                    self.assertEqual(second_envelope["sequence"], first_envelope["sequence"] + 1)

                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect(f"/ws/mobile?ticket={ticket}"):
                        pass

                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect(f"/ws/mobile?token={token}"):
                        pass

                expiring = client.post("/api/mobile/ws-ticket", headers=headers).json()["ticket"]
                now[0] += 31.0
                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect(f"/ws/mobile?ticket={expiring}"):
                        pass

                now[0] += 1.0
                revocable = client.post("/api/mobile/ws-ticket", headers=headers).json()["ticket"]
                main_app.state.revoke_mobile_device(claimed["device"]["id"])
                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect(f"/ws/mobile?ticket={revocable}"):
                        pass
            finally:
                main_app.state = previous_state
                main_app.auth = previous_auth
                if previous_monotonic is not None:
                    main_app.mobile_service._monotonic = previous_monotonic

    def test_active_mobile_websocket_is_invalidated_immediately_on_revoke(self) -> None:
        from app import main as main_app

        with TemporaryDirectory() as directory:
            previous_state = main_app.state
            previous_auth = main_app.auth
            main_app.state = self.make_state(directory)
            main_app.auth = AuthManager(password="desktop-pass")
            desktop_token = main_app.auth.login("desktop-pass")
            try:
                client = TestClient(main_app.app)
                pairing = main_app.state.create_mobile_pairing(
                    api_base_url="https://cryptoarc-node.tailnet.ts.net",
                    scopes=[MobileScope.MONITOR],
                )
                claimed = main_app.state.claim_mobile_pairing(
                    pairing["id"], pairing["code"], "Pixel 9", "android"
                )
                ticket = client.post(
                    "/api/mobile/ws-ticket",
                    headers={"Authorization": f"Bearer {claimed['token']}"},
                ).json()["ticket"]

                with client.websocket_connect(f"/ws/mobile?ticket={ticket}") as websocket:
                    self.assertEqual(websocket.receive_json()["event_type"], "cockpit")
                    revoked = client.post(
                        f"/api/mobile/devices/{claimed['device']['id']}/revoke",
                        headers={"Authorization": f"Bearer {desktop_token}"},
                    )
                    self.assertEqual(revoked.status_code, 200)
                    invalidation = websocket.receive_json()
                    self.assertEqual(invalidation["event_type"], "invalidate")
                    self.assertEqual(invalidation["payload"]["reason"], "token_revoked")
                    with self.assertRaises(WebSocketDisconnect):
                        websocket.receive_json()
            finally:
                main_app.state = previous_state
                main_app.auth = previous_auth

    def test_active_mobile_websocket_revalidates_expiry_scope_and_restore(self) -> None:
        from app import main as main_app

        for invalidation_case, expected_reason in (
            ("expiry", "token_expired"),
            ("scope", "device_scope_changed"),
            ("restore", "credentials_replaced"),
        ):
            with self.subTest(invalidation_case=invalidation_case), TemporaryDirectory() as directory:
                previous_state = main_app.state
                previous_auth = main_app.auth
                main_app.state = self.make_state(directory)
                main_app.auth = AuthManager(password="desktop-pass")
                desktop_token = main_app.auth.login("desktop-pass")
                try:
                    client = TestClient(main_app.app)
                    pairing = main_app.state.create_mobile_pairing(
                        api_base_url="https://cryptoarc-node.tailnet.ts.net",
                        scopes=[MobileScope.MONITOR],
                    )
                    claimed = main_app.state.claim_mobile_pairing(
                        pairing["id"], pairing["code"], "Pixel 9", "android"
                    )
                    ticket = client.post(
                        "/api/mobile/ws-ticket",
                        headers={"Authorization": f"Bearer {claimed['token']}"},
                    ).json()["ticket"]

                    with client.websocket_connect(f"/ws/mobile?ticket={ticket}") as websocket:
                        self.assertEqual(websocket.receive_json()["event_type"], "cockpit")
                        if invalidation_case == "restore":
                            with patch.object(
                                main_app.state,
                                "confirm_restore_artifact",
                                return_value={"status": "restored"},
                            ):
                                response = client.post(
                                    "/api/data/restore/confirm",
                                    json={"artifact": {"fixture": "validated-elsewhere"}},
                                    headers={"Authorization": f"Bearer {desktop_token}"},
                                )
                            self.assertEqual(response.status_code, 200, response.text)
                        else:
                            device = main_app.state.storage.load_mobile_device(
                                claimed["device"]["id"]
                            )
                            self.assertIsNotNone(device)
                            if invalidation_case == "expiry":
                                device["expires_at"] = (
                                    datetime.now(timezone.utc) - timedelta(seconds=1)
                                ).isoformat()
                            else:
                                device["scopes"] = []
                            main_app.state.storage.save_mobile_device(device)
                            response = client.post(
                                "/api/mobile/pairing/start",
                                json={
                                    "api_base_url": "https://cryptoarc-node.tailnet.ts.net"
                                },
                                headers={"Authorization": f"Bearer {desktop_token}"},
                            )
                            self.assertEqual(response.status_code, 200)

                        invalidation = websocket.receive_json()
                        self.assertEqual(invalidation["event_type"], "invalidate")
                        self.assertEqual(invalidation["payload"]["reason"], expected_reason)
                        with self.assertRaises(WebSocketDisconnect):
                            websocket.receive_json()
                finally:
                    main_app.state = previous_state
                    main_app.auth = previous_auth


if __name__ == "__main__":
    unittest.main()

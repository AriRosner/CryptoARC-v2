import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.auth import AuthManager
from app.core.models import BotStatus
from app.core.state import BotState


class MobileApiTests(unittest.TestCase):
    def make_state(self, directory: str) -> BotState:
        return BotState(database_path=str(Path(directory) / "test.db"))

    def test_mobile_pairing_claim_revocation_and_token_hashing(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)

            pairing = state.create_mobile_pairing(
                api_base_url="https://cryptoarc-node.tailnet.ts.net",
                scopes=["mobile:monitor", "mobile:control"],
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


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.state import BotState
from app.core.storage import Storage


class RevocationInterleavingStorage(Storage):
    """Forces a revoke at the legacy lookup/touch boundary."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.revoke_during_validation = False

    def _revoke_after_lookup(self, device: dict[str, object] | None) -> None:
        if not self.revoke_during_validation or not device:
            return
        self.revoke_during_validation = False
        current = super().load_mobile_device(str(device["id"]))
        assert current is not None
        current["revoked_at"] = "2026-07-19T00:00:00+00:00"
        super().save_mobile_device(current)

    def load_mobile_device_by_token_hash(self, token_hash: str) -> dict[str, object] | None:
        device = super().load_mobile_device_by_token_hash(token_hash)
        self._revoke_after_lookup(device)
        return device

    def touch_active_mobile_device_by_token_hash(
        self, token_hash: str, last_seen_at: str
    ) -> dict[str, object] | None:
        device = super().load_mobile_device_by_token_hash(token_hash)
        self._revoke_after_lookup(device)
        return super().touch_active_mobile_device_by_token_hash(token_hash, last_seen_at)


class MobileRevocationTests(unittest.TestCase):
    def test_token_validation_cannot_restore_a_device_revoked_during_validation(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "test.db")
            state = BotState(database_path=database_path)
            state.storage = RevocationInterleavingStorage(database_path)
            pairing = state.create_mobile_pairing(api_base_url="https://cryptoarc-node.tailnet.ts.net")
            claimed = state.claim_mobile_pairing(pairing["id"], pairing["code"], "Pixel 9", "android")

            state.storage.revoke_during_validation = True
            validated = state.validate_mobile_token(claimed["token"])
            persisted = state.storage.load_mobile_device(claimed["device"]["id"])

            self.assertIsNone(validated)
            self.assertTrue(str(persisted.get("revoked_at") or ""))

    def test_expired_token_does_not_update_last_seen(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            pairing = state.create_mobile_pairing(api_base_url="https://cryptoarc-node.tailnet.ts.net")
            claimed = state.claim_mobile_pairing(pairing["id"], pairing["code"], "Pixel 9", "android")
            device = state.storage.load_mobile_device(claimed["device"]["id"])
            assert device is not None
            device["expires_at"] = "2000-01-01T00:00:00+00:00"
            device["last_seen_at"] = "2000-01-01T00:00:00+00:00"
            state.storage.save_mobile_device(device)

            validated = state.validate_mobile_token(claimed["token"])
            persisted = state.storage.load_mobile_device(claimed["device"]["id"])

            self.assertIsNone(validated)
            self.assertEqual(persisted["last_seen_at"], "2000-01-01T00:00:00+00:00")

    def test_missing_scope_does_not_update_last_seen(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            pairing = state.create_mobile_pairing(
                api_base_url="https://cryptoarc-node.tailnet.ts.net", scopes=["mobile:monitor"]
            )
            claimed = state.claim_mobile_pairing(pairing["id"], pairing["code"], "Pixel 9", "android")
            device = state.storage.load_mobile_device(claimed["device"]["id"])
            assert device is not None
            device["last_seen_at"] = "2000-01-01T00:00:00+00:00"
            state.storage.save_mobile_device(device)

            validated = state.validate_mobile_token(claimed["token"], required_scope="mobile:control")
            persisted = state.storage.load_mobile_device(claimed["device"]["id"])

            self.assertIsNone(validated)
            self.assertEqual(persisted["last_seen_at"], "2000-01-01T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()

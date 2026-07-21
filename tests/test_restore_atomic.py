from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.core.models import BotSettings, BotStatus
from app.core.state import BotState
from app.core.storage import Storage


class AtomicRestoreTests(unittest.TestCase):
    @staticmethod
    def _unsafe_artifact(path: Path) -> dict[str, object]:
        source = Storage(str(path))
        settings = BotSettings()
        settings.live_active_backend_armed = True
        settings.kill_switch_enabled = False
        source.save_settings(settings)
        source.save_backup_restore_history(
            {
                "id": "source_history",
                "created_at": "2026-01-01T00:00:00+00:00",
                "action": "backup_artifact",
                "status": "created",
            }
        )
        return source.create_backup_artifact()

    @staticmethod
    def _seed_target(path: Path) -> Storage:
        target = Storage(str(path))
        settings = BotSettings()
        settings.live_active_backend_armed = False
        settings.kill_switch_enabled = True
        settings.watch_wallet_address = "original-target-wallet"
        target.save_settings(settings)
        target.save_backup_restore_history(
            {
                "id": "target_history",
                "created_at": "2026-01-02T00:00:00+00:00",
                "action": "backup_artifact",
                "status": "created",
            }
        )
        return target

    def test_staged_safe_write_failure_leaves_original_database_and_history_unchanged(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._unsafe_artifact(root / "source.db")
            target = self._seed_target(root / "target.db")
            original_bytes = target.path.read_bytes()
            original_history = target.load_backup_restore_history()
            original_save_settings = Storage.save_settings

            def fail_only_for_staged_database(storage: Storage, settings: BotSettings) -> None:
                if storage.path != target.path:
                    raise RuntimeError("injected staged safe-settings write failure")
                original_save_settings(storage, settings)

            with patch.object(Storage, "save_settings", new=fail_only_for_staged_database):
                with self.assertRaisesRegex(RuntimeError, "injected staged"):
                    target.restore_backup_artifact(artifact)

            self.assertEqual(target.path.read_bytes(), original_bytes)
            self.assertEqual(target.load_settings().watch_wallet_address, "original-target-wallet")
            self.assertEqual(target.load_backup_restore_history(), original_history)

    def test_safety_backup_copies_exact_original_without_removing_canonical_database(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._seed_target(Path(directory) / "target.db")
            original_bytes = target.path.read_bytes()

            with patch("app.core.storage.sqlite3.connect", side_effect=AssertionError("SQLite connection must not open")):
                backup_path = target._create_restore_safety_backup()

            self.assertTrue(target.path.exists())
            self.assertEqual(target.path.read_bytes(), original_bytes)
            self.assertEqual(backup_path.read_bytes(), original_bytes)

    def test_safety_backup_copy_failure_removes_partial_backup_and_preserves_canonical_database(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._seed_target(Path(directory) / "target.db")
            original_bytes = target.path.read_bytes()

            with patch("shutil.copyfileobj", side_effect=OSError("injected copy failure")):
                with self.assertRaisesRegex(OSError, "injected copy"):
                    target._create_restore_safety_backup()

            self.assertTrue(target.path.exists())
            self.assertEqual(target.path.read_bytes(), original_bytes)
            self.assertEqual(list(target.path.parent.glob(f"{target.path.stem}.backup-*{target.path.suffix}")), [])

    def test_post_swap_history_failure_atomically_restores_original_database(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._unsafe_artifact(root / "source.db")
            target = self._seed_target(root / "target.db")
            original_bytes = target.path.read_bytes()
            original_history = target.load_backup_restore_history()
            original_save_history = target.save_backup_restore_history

            def fail_success_history(payload: dict[str, object]) -> None:
                if payload.get("action") == "restore" and payload.get("status") == "restored":
                    raise RuntimeError("injected post-swap history failure")
                original_save_history(payload)

            target.save_backup_restore_history = fail_success_history

            with self.assertRaisesRegex(RuntimeError, "injected post-swap"):
                target.restore_backup_artifact(artifact)

            self.assertEqual(target.path.read_bytes(), original_bytes)
            restored_original = Storage(str(target.path))
            self.assertEqual(restored_original.load_settings().watch_wallet_address, "original-target-wallet")
            self.assertFalse(restored_original.load_settings().live_active_backend_armed)
            self.assertTrue(restored_original.load_settings().kill_switch_enabled)
            self.assertEqual(restored_original.load_backup_restore_history(), original_history)

    def test_missing_target_restores_without_preview_creating_an_invalid_database(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._unsafe_artifact(root / "source.db")
            target = Storage(str(root / "missing-target.db"))
            target.path.unlink()

            result = target.restore_backup_artifact(artifact)

            self.assertEqual(result["status"], "restored")
            self.assertTrue(target.path.exists())
            fresh = Storage(str(target.path))
            self.assertFalse(fresh.load_settings().live_active_backend_armed)
            self.assertTrue(fresh.load_settings().kill_switch_enabled)

    def test_botstate_reload_failure_rolls_back_exact_original_and_memory_fails_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._unsafe_artifact(root / "source.db")
            target_path = root / "target.db"
            target = BotState(database_path=str(target_path))
            target.settings.live_active_backend_armed = False
            target.settings.kill_switch_enabled = True
            target.settings.watch_wallet_address = "original-target-wallet"
            target.storage.save_settings(target.settings)
            original_bytes = target_path.read_bytes()

            def fail_reload() -> None:
                raise RuntimeError("injected BotState reload failure")

            target._reload_from_storage = fail_reload

            with self.assertRaisesRegex(RuntimeError, "injected BotState reload"):
                target.confirm_restore_artifact(artifact)

            self.assertEqual(target_path.read_bytes(), original_bytes)
            self.assertEqual(target.status, BotStatus.STOPPED)
            self.assertFalse(target.settings.live_active_backend_armed)
            self.assertTrue(target.settings.kill_switch_enabled)
            original = Storage(str(target_path))
            self.assertEqual(original.load_settings().watch_wallet_address, "original-target-wallet")

    def test_fail_once_validator_recovery_reload_does_not_mutate_rolled_back_original(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._unsafe_artifact(root / "source.db")
            target_path = root / "target.db"
            target = BotState(database_path=str(target_path))
            target.settings.live_active_backend_armed = False
            target.settings.kill_switch_enabled = True
            target.settings.watch_wallet_address = "original-target-wallet"
            target.storage.save_settings(target.settings)
            original_bytes = target_path.read_bytes()
            original_history = target.storage.load_backup_restore_history()
            original_settings_versions = target.storage.load_settings_versions(100)
            original_reload = target._reload_from_storage
            reload_calls = 0
            recovery_completed = False

            def fail_once_reload(persist_settings_version: bool = True) -> None:
                nonlocal recovery_completed, reload_calls
                reload_calls += 1
                if reload_calls == 1:
                    raise RuntimeError("injected one-time validator failure")
                original_reload(persist_settings_version=persist_settings_version)
                recovery_completed = True

            target._reload_from_storage = fail_once_reload

            with self.assertRaisesRegex(RuntimeError, "injected one-time validator"):
                target.confirm_restore_artifact(artifact)

            self.assertEqual(reload_calls, 2)
            self.assertTrue(recovery_completed)
            self.assertEqual(target_path.read_bytes(), original_bytes)
            recovered = Storage(str(target_path))
            self.assertEqual(recovered.load_backup_restore_history(), original_history)
            self.assertEqual(
                [item.to_dict() for item in recovered.load_settings_versions(100)],
                [item.to_dict() for item in original_settings_versions],
            )
            self.assertEqual(recovered.load_settings().watch_wallet_address, "original-target-wallet")
            self.assertEqual(target.status, BotStatus.STOPPED)
            self.assertFalse(target.settings.live_active_backend_armed)
            self.assertTrue(target.settings.kill_switch_enabled)

    def test_unsafe_artifact_is_persisted_safe_without_post_restore_settings_write(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._unsafe_artifact(root / "source.db")
            target_path = root / "target.db"
            target = BotState(database_path=str(target_path))
            target.settings.live_active_backend_armed = False
            target.settings.kill_switch_enabled = True
            target.storage.save_settings(target.settings)

            def reject_post_restore_write(_settings: BotSettings) -> None:
                raise RuntimeError("post-restore settings write must not run")

            target.storage.save_settings = reject_post_restore_write

            result = target.confirm_restore_artifact(artifact)

            self.assertEqual(result["status"], "restored")
            self.assertEqual(target.status, BotStatus.STOPPED)
            self.assertFalse(target.settings.live_active_backend_armed)
            self.assertTrue(target.settings.kill_switch_enabled)
            fresh = BotState(database_path=str(target_path))
            self.assertFalse(fresh.settings.live_active_backend_armed)
            self.assertTrue(fresh.settings.kill_switch_enabled)


if __name__ == "__main__":
    unittest.main()

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


HELPER = Path(__file__).parents[1] / "root" / "vzn-storage-maintenance"
loader = importlib.machinery.SourceFileLoader("storage_maintenance", str(HELPER))
spec = importlib.util.spec_from_loader(loader.name, loader)
maintenance = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = maintenance
loader.exec_module(maintenance)


class StorageMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.app = root / "app"
        self.releases = self.app / "releases"
        self.data_backups = self.app / "data" / "backups"
        self.backups = root / "backups"
        self.auto = root / "auto"
        self.state = root / "state"
        for directory in (self.releases, self.data_backups, self.backups, self.auto, self.state):
            directory.mkdir(parents=True, exist_ok=True)
        self.registry = self.state / "recovery-points.json"
        self.lock = self.auto / "lock"
        self.values = {
            "APP": self.app, "RELEASES": self.releases, "DATA_BACKUPS": self.data_backups,
            "BACKUPS": self.backups, "AUTO_STATE": self.auto, "STATE": self.state,
            "REGISTRY": self.registry, "LOCK": self.lock,
        }
        self.patch = patch.multiple(maintenance, **self.values)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temporary.cleanup()

    def point(self, suffix, image=None):
        commit = suffix * 40
        release = self.releases / f"20261126T12000{suffix}Z-{'a' * 11}{suffix}"
        release.mkdir()
        transaction = self.backups / f"update-{release.name}.fixture"
        transaction.mkdir()
        backup = self.data_backups / f"vzn-20261126T12000{suffix}Z.sqlite3"
        backup.touch()
        return {
            "commit": commit,
            "release": str(release),
            "image": image or f"vzn-activity-tracker-backend:ci-{commit}",
            "transaction": str(transaction),
            "backup": str(backup),
            "recorded_at": f"2026-11-26T12:00:0{suffix}+00:00",
            "status": "successful",
            "ci_run_id": 1,
            "compose_sha256": "b" * 64,
        }

    def registry_with_current(self, count=1):
        points = [self.point(str(index)) for index in range(1, count + 1)]
        current = self.app / "current"
        current.symlink_to(points[-1]["release"])
        return {"version": 1, "points": points}

    def test_current_and_three_previous_recovery_points_are_protected(self):
        registry = self.registry_with_current(5)
        retained = maintenance.protected_points(registry)
        self.assertEqual([point["commit"] for point in retained], ["5" * 40, "4" * 40, "3" * 40, "2" * 40])
        planned = maintenance.candidates(registry)
        self.assertEqual([item.kind for item in planned if item.kind == "release"], ["release"])
        self.assertEqual(planned[0].path, registry["points"][0]["release"])

    def test_legacy_release_without_metadata_is_never_a_candidate(self):
        registry = self.registry_with_current()
        legacy = self.releases / "20261125T120000Z-cccccccccccc"
        legacy.mkdir()
        self.assertFalse(any(item.path == str(legacy) for item in maintenance.candidates(registry)))

    def test_dry_run_candidate_does_not_delete_staging(self):
        registry = self.registry_with_current()
        staging = self.backups / "staged-update-20261125T000000Z-aaaaaaaaaaaa"
        for child in ("source", "frontend", "backend", "deployment"):
            (staging / child).mkdir(parents=True)
        os.utime(staging, (time.time() - maintenance.STALE_SECONDS - 1,) * 2)
        with patch.object(maintenance, "root_directory", return_value=None):
            planned = maintenance.candidates(registry)
        self.assertTrue(any(item.path == str(staging) and item.kind == "staging" for item in planned))
        self.assertTrue(staging.exists())

    def test_active_or_interrupted_operation_blocks_cleanup_candidates(self):
        registry = self.registry_with_current()
        (self.app / ".vzn-updating").touch()
        with self.assertRaisesRegex(maintenance.SafetyError, "marker"):
            maintenance.candidates(registry)

    def test_symlink_cannot_escape_deletion_root(self):
        root = self.backups / "staged-update-20261125T000000Z-bbbbbbbbbbbb"
        root.mkdir()
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (root / "escape").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(maintenance.SafetyError, "symlink"):
            maintenance.remove_tree(root)
        self.assertTrue(outside.exists())

    def test_image_with_container_or_extra_tag_is_protected(self):
        tag = "vzn-activity-tracker-backend:ci-" + "a" * 40
        response = type("Response", (), {"returncode": 0, "stdout": "sha256:image [\"" + tag + "\",\"other:tag\"]\n"})()
        with patch.object(maintenance.subprocess, "run", return_value=response):
            self.assertFalse(maintenance.docker_safe_to_remove(tag))

    def test_corrupted_metadata_fails_closed(self):
        registry = self.registry_with_current()
        registry["points"][0]["backup"] = "../../outside"
        with self.assertRaisesRegex(maintenance.SafetyError, "invalid"):
            maintenance.protected_points(registry)


if __name__ == "__main__":
    unittest.main()

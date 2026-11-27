from contextlib import contextmanager
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
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

    def test_cleanup_accepts_the_inherited_worker_lock(self):
        self.lock.touch()
        with self.lock.open("a+") as lock, \
                patch.object(maintenance.os, "geteuid", return_value=0), \
                patch.object(maintenance, "root_directory"), \
                patch.object(maintenance, "candidates", return_value=[]), \
                patch.dict(os.environ, {"VZN_OPERATION_LOCK_FD": str(lock.fileno())}):
            maintenance.fcntl.flock(lock, maintenance.fcntl.LOCK_EX)
            self.assertEqual(maintenance.run_cleanup(apply=False), 0)

    @contextmanager
    def cleanup_environment(self, *, removable=True, tag_present=False):
        with patch.object(maintenance.os, "geteuid", return_value=0), \
                patch.object(maintenance, "root_directory"), \
                patch.object(maintenance, "root_regular"), \
                patch.object(maintenance, "docker_safe_to_remove", return_value=removable), \
                patch.object(maintenance, "docker_tag_present", return_value=tag_present), \
                patch.object(maintenance.subprocess, "run") as docker:
            yield docker

    def save_registry(self, registry):
        self.registry.write_text(json.dumps(registry), encoding="utf-8")

    def read_registry(self):
        return json.loads(self.registry.read_text(encoding="utf-8"))

    def test_two_applied_cleanups_keep_registry_consistent(self):
        registry = self.registry_with_current(7)
        self.save_registry(registry)
        with self.cleanup_environment() as docker:
            self.assertEqual(maintenance.run_cleanup(apply=True), 0)
            first = self.registry.read_bytes()
            self.assertEqual(maintenance.run_cleanup(apply=True), 0)
        self.assertEqual(first, self.registry.read_bytes())
        self.assertEqual(self.read_registry()["points"], registry["points"][3:])
        self.assertEqual(self.read_registry()["pending_images"], [])
        self.assertEqual(docker.call_count, 3)
        self.assertFalse(maintenance.intent_path().exists())
        self.assertTrue(all(not Path(point["release"]).exists() for point in registry["points"][:3]))
        self.assertTrue(all(Path(point["release"]).is_dir() for point in registry["points"][3:]))
        self.assertTrue(all(Path(point["backup"]).is_file() and Path(point["transaction"]).is_dir()
                            for point in registry["points"]))

    def test_failed_release_deletion_preserves_point_and_can_retry(self):
        registry = self.registry_with_current(5)
        self.save_registry(registry)
        release = Path(registry["points"][0]["release"])
        (release / "partially-removed").touch()

        def partial_failure(path):
            (path / "partially-removed").unlink()
            raise OSError("failed")

        with self.cleanup_environment(), patch.object(maintenance, "remove_tree", side_effect=partial_failure):
            with self.assertRaisesRegex(OSError, "failed"):
                maintenance.run_cleanup(apply=True)
        self.assertEqual(self.read_registry(), registry)
        self.assertTrue(maintenance.intent_path().is_file())
        self.assertTrue(Path(registry["points"][0]["release"]).is_dir())
        with self.cleanup_environment():
            self.assertEqual(maintenance.run_cleanup(apply=True), 0)
        self.assertEqual(self.read_registry()["points"], registry["points"][1:])

    def test_interruption_after_release_removal_before_registry_write(self):
        registry = self.registry_with_current(5)
        self.save_registry(registry)
        original = maintenance.atomic_json

        def interrupted(path, value):
            if path == self.registry:
                raise OSError("interrupted registry write")
            original(path, value)

        with self.cleanup_environment(), patch.object(maintenance, "atomic_json", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "interrupted"):
                maintenance.run_cleanup(apply=True)
        self.assertEqual(self.read_registry(), registry)
        self.assertFalse(Path(registry["points"][0]["release"]).exists())
        intent = maintenance.intent_path().read_bytes()
        before = self.registry.read_bytes()
        with self.cleanup_environment():
            self.assertEqual(maintenance.run_cleanup(apply=False), 0)
        self.assertEqual(self.registry.read_bytes(), before)
        self.assertEqual(maintenance.intent_path().read_bytes(), intent)
        with self.cleanup_environment():
            self.assertEqual(maintenance.run_cleanup(apply=True), 0)
        self.assertEqual(self.read_registry()["points"], registry["points"][1:])
        self.assertFalse(maintenance.intent_path().exists())

    def test_interruption_after_registry_write_before_intent_removal(self):
        registry = self.registry_with_current(5)
        self.save_registry(registry)
        with self.cleanup_environment(), patch.object(maintenance, "clear_intent", side_effect=OSError("interrupted")):
            with self.assertRaisesRegex(OSError, "interrupted"):
                maintenance.run_cleanup(apply=True)
        self.assertEqual(self.read_registry()["points"], registry["points"][1:])
        self.assertEqual(self.read_registry()["pending_images"], [registry["points"][0]["image"]])
        self.assertTrue(maintenance.intent_path().is_file())
        with self.cleanup_environment():
            self.assertEqual(maintenance.run_cleanup(apply=True), 0)
        self.assertFalse(maintenance.intent_path().exists())
        self.assertEqual(self.read_registry()["pending_images"], [])

    def test_unexplained_missing_release_still_blocks_all_cleanup(self):
        registry = self.registry_with_current(6)
        self.save_registry(registry)
        point = registry["points"][0]
        Path(point["release"]).rmdir()
        with self.cleanup_environment() as docker:
            with self.assertRaisesRegex(maintenance.SafetyError, point["commit"]):
                maintenance.run_cleanup(apply=True)
        self.assertEqual(self.read_registry(), registry)
        self.assertTrue(Path(registry["points"][1]["release"]).is_dir())
        docker.assert_not_called()

    def test_dry_run_never_retires_points_or_images(self):
        registry = self.registry_with_current(5)
        self.save_registry(registry)
        before = self.registry.read_bytes()
        with self.cleanup_environment() as docker:
            self.assertEqual(maintenance.run_cleanup(apply=False), 0)
        self.assertEqual(self.registry.read_bytes(), before)
        self.assertFalse(maintenance.intent_path().exists())
        self.assertTrue(Path(registry["points"][0]["release"]).is_dir())
        docker.assert_not_called()

    def test_protected_image_is_queued_and_retried_later(self):
        registry = self.registry_with_current(5)
        self.save_registry(registry)
        image = registry["points"][0]["image"]
        with self.cleanup_environment(removable=False, tag_present=True) as docker:
            maintenance.run_cleanup(apply=True)
        docker.assert_not_called()
        self.assertEqual(self.read_registry()["pending_images"], [image])
        self.assertEqual(self.read_registry()["points"], registry["points"][1:])
        with self.cleanup_environment() as docker:
            maintenance.run_cleanup(apply=True)
        docker.assert_called_once_with(["/usr/bin/docker", "image", "rm", image], check=True)
        self.assertEqual(self.read_registry()["pending_images"], [])

    def test_failed_image_removal_preserves_pending_tag(self):
        registry = self.registry_with_current(5)
        self.save_registry(registry)
        image = registry["points"][0]["image"]
        with self.cleanup_environment() as docker:
            docker.side_effect = subprocess.CalledProcessError(1, "docker")
            with self.assertRaises(subprocess.CalledProcessError):
                maintenance.run_cleanup(apply=True)
        self.assertEqual(self.read_registry()["pending_images"], [image])
        self.assertEqual(self.read_registry()["points"], registry["points"][1:])
        with self.cleanup_environment(removable=False, tag_present=False) as docker:
            maintenance.run_cleanup(apply=True)
        docker.assert_not_called()
        self.assertEqual(self.read_registry()["pending_images"], [])

    def test_pending_image_shared_with_current_is_not_a_candidate(self):
        registry = self.registry_with_current(5)
        image = registry["points"][-1]["image"]
        registry["points"][0]["image"] = image
        self.save_registry(registry)
        with self.cleanup_environment() as docker:
            maintenance.run_cleanup(apply=True)
            maintenance.run_cleanup(apply=True)
        docker.assert_not_called()
        self.assertEqual(self.read_registry()["pending_images"], [image])

    def test_current_is_protected_even_when_older_than_latest_four(self):
        registry = self.registry_with_current(6)
        (self.app / "current").unlink()
        (self.app / "current").symlink_to(registry["points"][0]["release"])
        planned = maintenance.candidates(registry)
        self.assertFalse(any(item.path == registry["points"][0]["release"] for item in planned))
        self.assertEqual([item.path for item in planned if item.kind == "release"],
                         [registry["points"][1]["release"]])

    def test_same_parent_symlink_is_not_a_valid_recovery_release(self):
        registry = self.registry_with_current(5)
        point = registry["points"][0]
        release = Path(point["release"])
        release.rmdir()
        release.symlink_to(registry["points"][1]["release"])
        with self.assertRaisesRegex(maintenance.SafetyError, point["commit"]):
            maintenance.candidates(registry)

    def test_intent_cannot_authorize_deletion_of_current_release(self):
        registry = self.registry_with_current(5)
        self.save_registry(registry)
        point = registry["points"][-1]
        metadata = Path(point["release"]).lstat()
        with self.cleanup_environment() as docker:
            maintenance.atomic_json(maintenance.intent_path(), {
                "version": 1, "point": point, "device": metadata.st_dev, "inode": metadata.st_ino,
            })
            with self.assertRaisesRegex(maintenance.SafetyError, "protected recovery point"):
                maintenance.run_cleanup(apply=True)
        docker.assert_not_called()
        self.assertEqual(self.read_registry(), registry)
        self.assertTrue(Path(point["release"]).is_dir())

    def test_intent_rejects_replaced_directory(self):
        registry = self.registry_with_current(5)
        self.save_registry(registry)
        point = registry["points"][0]
        release = Path(point["release"])
        with self.cleanup_environment() as docker:
            maintenance.begin_release_cleanup(registry, point)
            release.rename(self.backups / "original-release")
            release.mkdir()
            with self.assertRaisesRegex(maintenance.SafetyError, "identity changed"):
                maintenance.run_cleanup(apply=True)
        self.assertEqual(self.read_registry(), registry)
        self.assertTrue(release.is_dir())
        docker.assert_not_called()

    def test_intent_does_not_hide_unrelated_missing_release(self):
        registry = self.registry_with_current(6)
        self.save_registry(registry)
        with self.cleanup_environment() as docker:
            maintenance.begin_release_cleanup(registry, registry["points"][0])
            unrelated = registry["points"][1]
            Path(unrelated["release"]).rmdir()
            with self.assertRaisesRegex(maintenance.SafetyError, unrelated["commit"]):
                maintenance.run_cleanup(apply=True)
        self.assertEqual(self.read_registry(), registry)
        self.assertTrue(Path(registry["points"][0]["release"]).is_dir())
        docker.assert_not_called()

    def test_docker_tag_listing_failure_is_not_evidence_of_absence(self):
        image = "vzn-activity-tracker-backend:ci-" + "a" * 40
        with patch.object(maintenance.subprocess, "run",
                          side_effect=subprocess.CalledProcessError(1, "docker")):
            with self.assertRaises(subprocess.CalledProcessError):
                maintenance.docker_tag_present(image)
        with patch.object(maintenance.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, stdout=image + "\n")):
            self.assertTrue(maintenance.docker_tag_present(image))
        with patch.object(maintenance.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, stdout="other:tag\n")):
            self.assertFalse(maintenance.docker_tag_present(image))

    def test_inherited_lock_rejects_a_different_file(self):
        self.lock.touch()
        other = self.state / "other-lock"
        other.touch()
        with other.open() as stream, patch.dict(
                os.environ, {"VZN_OPERATION_LOCK_FD": str(stream.fileno())}):
            with self.assertRaisesRegex(maintenance.SafetyError, "does not match"):
                maintenance.inherited_lock()


if __name__ == "__main__":
    unittest.main()

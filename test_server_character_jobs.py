import copy
import json
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import requests
from cryptography.fernet import Fernet

from background_jobs import JobProgress
from background_registry import JobRegistry
from browser_session_store import encode_browser_backup, decode_browser_backup
from server_character_jobs import (
    start_character_job, collect_character_jobs, profile_job, profile_data,
    run_character_job, save_character_checkpoint, SupersededProfileJob,
)
from test_character_profiles import scan, sheet
from video_scene_planner import source_fingerprint


class ServerCharacterTests(unittest.TestCase):
    def setUp(self):
        self.sid = uuid.uuid4().hex
        self.other = uuid.uuid4().hex
        self.record = {"name": "Story", "translated": "Tấm gặp Cám", "language": "vi",
                       "character_profile_json": "{}", "saved_order": 1}
        self.workspaces = {self.sid: self.record, self.other: {
            "name": "Other", "translated": "Do not change", "saved_order": 2,
        }}
        self.snapshot = {"translated": self.record["translated"], "language": "vi",
                         "style": "2D", "provider": "OpenAI", "model": "test-model",
                         "base_url": "https://api.openai.com/v1", "api_key": "PRIVATE_KEY",
                         "cloud": None}
        self.registry, self.jobs = JobRegistry(), {}
        self.scope = "characters:account:owner"
        self.release, self.started = threading.Event(), threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.addCleanup(self.executor.shutdown, wait=True)
        self.addCleanup(self.release.set)

    def launch(self, persist=lambda: None):
        return start_character_job(self.record, self.sid, self.snapshot, self.executor,
                                   self.registry, self.jobs, self.scope, persist)

    def blocked_ai(self, _snapshot, prompt):
        self.started.set()
        if not self.release.wait(15):
            raise RuntimeError("Test did not release worker")
        if "SINGLE CHARACTER TASK" in prompt:
            name = json.loads(prompt.split("named ")[-1].split(". Other names")[0])
            return sheet(name)
        return scan("Tấm", "Cám")

    def backup(self):
        return encode_browser_backup({"workspaces": self.workspaces,
            "selected_session": self.sid, "saved_session_order": 2})

    def test_real_worker_survives_navigation_and_browser_reload(self):
        with patch("server_character_jobs._provider_call", side_effect=self.blocked_ai) as ai:
            self.launch()
            self.assertTrue(self.started.wait(5))
            future = self.jobs[self.sid]["future"]
            old_backup = self.backup()
            self.assertNotIn("PRIVATE_KEY", old_backup)
            restored = decode_browser_backup(old_backup)["workspaces"]
            new_jobs = {}
            collect_character_jobs(restored, new_jobs, self.registry, self.scope)
            self.assertIs(new_jobs[self.sid]["future"], future)
            self.assertFalse(future.done())
            # No UI polls while the complete worker finishes.
            self.release.set()
            self.assertTrue(future.result(timeout=10)["ok"])
            collect_character_jobs(restored, new_jobs, self.registry, self.scope)
            self.assertEqual(profile_job(restored[self.sid])["state"], "completed")
            self.assertEqual(len(profile_data(restored[self.sid])["characters"]), 2)
            self.assertEqual(restored[self.other]["translated"], "Do not change")
            self.assertEqual(ai.call_count, 3)
            # Reloading the older running snapshot again still retrieves the
            # retained final result instead of starting a second paid job.
            again = decode_browser_backup(old_backup)["workspaces"]
            collect_character_jobs(again, {}, self.registry, self.scope)
            self.assertEqual(profile_job(again[self.sid])["state"], "completed")
            self.assertEqual(ai.call_count, 3)

    def test_duplicate_start_reattaches_without_another_request(self):
        with patch("server_character_jobs._provider_call", side_effect=self.blocked_ai):
            self.launch()
            future = self.jobs[self.sid]["future"]
            self.jobs.clear()
            self.assertFalse(self.launch())
            self.assertIs(self.jobs[self.sid]["future"], future)
            self.release.set()
            self.assertTrue(future.result(timeout=10)["ok"])

    def test_another_account_cannot_reattach_to_worker(self):
        with patch("server_character_jobs._provider_call", side_effect=self.blocked_ai):
            self.launch()
            future = self.jobs[self.sid]["future"]
            untrusted = copy.deepcopy(self.workspaces)
            other_jobs = {}
            collect_character_jobs(untrusted, other_jobs, self.registry, "characters:account:other")
            self.assertEqual(other_jobs, {})
            self.assertEqual(profile_job(untrusted[self.sid])["state"], "interrupted")
            self.release.set()
            self.assertTrue(future.result(timeout=10)["ok"])

    def test_translation_change_or_deletion_prevents_stale_results(self):
        for deleted in (False, True):
            with self.subTest(deleted=deleted), patch(
                "server_character_jobs._provider_call", side_effect=self.blocked_ai,
            ):
                self.release.clear()
                self.started.clear()
                self.record["translated"] = self.snapshot["translated"]
                self.record["character_profile_json"] = "{}"
                self.workspaces[self.sid] = self.record
                self.launch()
                self.assertTrue(self.started.wait(5))
                future = self.jobs[self.sid]["future"]
                if deleted:
                    del self.workspaces[self.sid]
                else:
                    self.record["translated"] = "New story"
                collect_character_jobs(self.workspaces, self.jobs, self.registry, self.scope)
                self.release.set()
                future.result(timeout=10)
                self.assertNotIn(self.sid, self.jobs)
                if not deleted:
                    self.assertEqual(self.record["translated"], "New story")
                    self.assertNotIn("characters", profile_data(self.record))

    def test_temporary_timeout_is_retried_without_browser(self):
        # Generate a realistic wrapped timeout from the API client.
        try:
            try:
                raise requests.ReadTimeout("PRIVATE_KEY")
            except requests.ReadTimeout as exc:
                raise RuntimeError("Timeout") from exc
        except RuntimeError as exc:
            timeout = exc
        self.release.set()
        with patch("server_character_jobs._provider_call", side_effect=[
            timeout, scan("Tấm"), sheet("Tấm"),
        ]) as ai, patch("server_character_jobs.time.sleep"):
            self.launch()
            future = self.jobs[self.sid]["future"]
            outcome = future.result(timeout=10)
        self.assertTrue(outcome["ok"], outcome["error"])
        self.assertEqual(ai.call_count, 3)
        self.assertNotIn("PRIVATE_KEY", json.dumps(outcome))

    def cloud_fixture(self):
        run_id = uuid.uuid4().hex
        self.record["character_profile_json"] = json.dumps({"_profile_job": {
            "run_id": run_id, "state": "running",
            "source_hash": source_fingerprint(self.snapshot["translated"], "vi"),
        }})
        snapshot = dict(self.snapshot, sid=self.sid, run_id=run_id,
                        character_profile_json=self.record["character_profile_json"])
        snapshot["cloud"] = {
            "auth": {"user_id": "owner", "access_token": "jwt", "expires_at": time.time() + 900},
            "secrets": {"SUPABASE_URL": "https://example.supabase.co",
                        "SUPABASE_ANON_KEY": "public", "SESSION_ENCRYPTION_KEY": Fernet.generate_key().decode()},
        }
        return snapshot

    def test_cloud_checkpoint_preserves_other_sessions_and_scopes_user(self):
        snapshot = self.cloud_fixture()
        payload = {"workspaces": copy.deepcopy(self.workspaces)}
        fields = {"character_profile_json": snapshot["character_profile_json"],
                  "character_bible": "Tấm: reference", "translated": "MUST NOT REPLACE"}
        with patch("persistent_store._request", return_value=[{
            "payload": payload, "encrypted_config": "",
        }]) as reader, patch("persistent_store.save_user") as saver:
            save_character_checkpoint(snapshot, fields)
        saved = saver.call_args.args[2]["workspaces"]
        self.assertEqual(saved[self.sid]["translated"], self.snapshot["translated"])
        self.assertEqual(saved[self.sid]["character_bible"], "Tấm: reference")
        self.assertEqual(saved[self.other]["translated"], "Do not change")
        self.assertEqual(reader.call_args.kwargs["params"]["user_id"], "eq.owner")

    def test_deleted_or_replaced_cloud_job_is_never_written(self):
        snapshot = self.cloud_fixture()
        payload = {"workspaces": {}}
        with patch("persistent_store._request", return_value=[{
            "payload": payload, "encrypted_config": "",
        }]), patch("persistent_store.save_user") as saver:
            with self.assertRaises(SupersededProfileJob):
                save_character_checkpoint(snapshot, {})
        saver.assert_not_called()

    def test_storage_failure_does_not_stop_worker_or_lose_results(self):
        snapshot = self.cloud_fixture()
        progress = JobProgress()
        with patch("server_character_jobs._provider_call", side_effect=[scan("Tấm"), sheet("Tấm")]), patch(
            "server_character_jobs.save_character_checkpoint", side_effect=RuntimeError("network"),
        ):
            result = run_character_job(snapshot, progress)
        self.assertTrue(result["ok"])
        meta = json.loads(result["fields"]["character_profile_json"])["_profile_job"]
        self.assertEqual(meta["state"], "completed")
        self.assertIn("save_error", meta)


if __name__ == "__main__":
    unittest.main()

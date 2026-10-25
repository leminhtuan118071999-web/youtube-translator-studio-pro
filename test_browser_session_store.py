"""Browser session backup regression tests (no Streamlit runtime needed)."""
import json
import unittest
import uuid

from browser_session_store import (
    STORAGE_KEY, encode_browser_backup, decode_browser_backup,
)


class BrowserSessionBackupTests(unittest.TestCase):
    def setUp(self):
        self.first_id = uuid.uuid4().hex
        self.second_id = uuid.uuid4().hex
        self.payload = {
            "selected_session": self.second_id,
            "saved_session_order": 2,
            "workspaces": {
                self.first_id: {
                    "name": "Video số 1", "url": "https://youtu.be/test",
                    "translated": "Bản dịch " * 320,
                    "prompts": "Prompt " * 650,
                    "job_state": "completed", "saved_order": 1,
                    "processed": True, "saved": True,
                    "api_key": "THIS_MUST_NOT_BE_STORED",
                },
                self.second_id: {
                    "name": "Video số 2", "job_state": "failed",
                    "job_error": "Provider failed", "saved_order": 2,
                    "processed": True, "saved": True,
                },
            },
        }

    def test_all_sessions_and_order_survive_round_trip(self):
        encoded = encode_browser_backup(self.payload)
        result = decode_browser_backup(encoded)
        self.assertEqual(result["selected_session"], self.second_id)
        self.assertEqual(result["saved_session_order"], 2)
        self.assertEqual(set(result["workspaces"]), {self.first_id, self.second_id})
        self.assertEqual(result["workspaces"][self.first_id]["name"], "Video số 1")
        self.assertIn("Bản dịch", result["workspaces"][self.first_id]["translated"])
        self.assertEqual(result["workspaces"][self.second_id]["job_state"], "failed")
        self.assertNotIn("api_key", result["workspaces"][self.first_id])
        self.assertNotIn("THIS_MUST_NOT_BE_STORED", encoded)

    def test_running_job_restores_as_interrupted_not_running(self):
        self.payload["workspaces"][self.first_id]["job_state"] = "running"
        restored = decode_browser_backup(encode_browser_backup(self.payload))
        self.assertEqual(
            restored["workspaces"][self.first_id]["job_state"], "interrupted"
        )

    def test_corrupt_browser_backup_fails_closed(self):
        encoded = json.loads(encode_browser_backup(self.payload))
        encoded["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            decode_browser_backup(json.dumps(encoded))
        with self.assertRaises(ValueError):
            decode_browser_backup("not-json")
        with self.assertRaises(ValueError):
            decode_browser_backup(None)

    def test_deleted_session_not_resurrected(self):
        self.payload["workspaces"].pop(self.first_id)
        new_snapshot = decode_browser_backup(encode_browser_backup(self.payload))
        self.assertEqual(list(new_snapshot["workspaces"]), [self.second_id])

    def test_delete_all_replaces_snapshot_with_new_empty_workspace(self):
        old_ids = set(self.payload["workspaces"])
        fresh_id = uuid.uuid4().hex
        self.payload = {
            "selected_session": fresh_id,
            "saved_session_order": 1,
            "workspaces": {
                fresh_id: {
                    "name": "Phiên 1",
                    "processed": False,
                    "saved": False,
                    "saved_order": 1,
                    "translated": "",
                    "prompts": "",
                    "metadata": "",
                }
            },
        }
        reloaded = decode_browser_backup(encode_browser_backup(self.payload))
        self.assertEqual(set(reloaded["workspaces"]), {fresh_id})
        self.assertTrue(old_ids.isdisjoint(reloaded["workspaces"]))
        self.assertNotIn("Bản dịch", str(reloaded))
        self.assertNotIn("Provider failed", str(reloaded))

    def test_key_is_scoped_to_lmt_studio(self):
        self.assertIn("lmt-studio-pro", STORAGE_KEY)


if __name__ == "__main__":
    unittest.main()

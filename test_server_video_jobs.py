"""Server worker tests: independent of browser, isolated account checkpoint."""
import json
import unittest
import uuid
from unittest.mock import patch
from background_jobs import JobProgress
from server_video_jobs import run_video_forms_job, save_cloud_video_checkpoint
from video_scene_planner import narration_plan


class BackgroundVideoTests(unittest.TestCase):
    def setUp(self):
        self.sid = uuid.uuid4().hex
        self.run_id = uuid.uuid4().hex
        self.script = " ".join(["story"] * 1400)
        self.snapshot = {
            "sid": self.sid, "run_id": self.run_id,
            "translated": self.script, "language": "Tiếng Anh",
            "duration_seconds": 870.24, "audio_hash": "hash",
            "audio_name": "speech.mp3", "style": "Hoạt hình 2D",
            "character_bible": "Ala: black hair, red jacket.",
            "existing_plan": None, "provider": "Groq",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "openai/gpt-oss-20b",
            "api_key": "PRIVATE", "cloud": None,
        }

    def ai(self, _snapshot, prompt):
        rows = json.loads(prompt.split("Input scenes:\n", 1)[1])
        return json.dumps({"scenes": [
            {"number": row["number"], "visual_prompt": "Ala walks.",
             "transition_to_next": "crossfade 1.0s"} for row in rows
        ]})

    def test_109_forms_continue_without_client_polling(self):
        progress = JobProgress()
        with patch("server_video_jobs._provider_call", side_effect=self.ai) as vendor:
            outcome = run_video_forms_job(self.snapshot, progress)
        self.assertTrue(outcome["ok"], outcome["error"])
        plan = json.loads(outcome["fields"]["video_forms"])
        self.assertEqual(len(plan["scenes"]), 109)
        self.assertEqual(vendor.call_count, 19)
        self.assertTrue(all(s["visual_prompt"] for s in plan["scenes"]))
        self.assertEqual(progress.snapshot()[0], 100)

    def test_error_keeps_completed_batches_then_resumes(self):
        called = 0
        def unreliable(snapshot, prompt):
            nonlocal called
            called += 1
            if called == 3:
                raise RuntimeError("Provider 502")
            return self.ai(snapshot, prompt)
        with patch("server_video_jobs._provider_call", side_effect=unreliable):
            failed = run_video_forms_job(self.snapshot, JobProgress())
        self.assertFalse(failed["ok"])
        first = json.loads(failed["fields"]["video_forms"])
        self.assertEqual(sum(bool(s["visual_prompt"]) for s in first["scenes"]), 12)
        self.snapshot["existing_plan"] = failed["fields"]["video_forms"]
        with patch("server_video_jobs._provider_call", side_effect=self.ai) as vendor:
            resumed = run_video_forms_job(self.snapshot, JobProgress())
        self.assertTrue(resumed["ok"])
        self.assertEqual(vendor.call_count, 17)
        final = json.loads(resumed["fields"]["video_forms"])
        self.assertEqual(len([s for s in final["scenes"] if s["visual_prompt"]]), 109)

    def test_cloud_checkpoint_changes_only_active_session(self):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        uid = str(uuid.uuid4())
        payload = {"workspaces": {
            self.sid: {"video_job_run_id": self.run_id, "video_forms": ""},
            uuid.uuid4().hex: {"name": "other", "translated": "preserved"},
        }}
        import time
        self.snapshot["cloud"] = {
            "secrets": {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_ANON_KEY": "public",
                "SESSION_ENCRYPTION_KEY": key,
            },
            "auth": {
                "user_id": uid, "access_token": "user-jwt",
                "refresh_token": "rotating-secret", "expires_at": time.time()+900,
            },
        }
        plan = narration_plan("one two three four", "Tiếng Anh", audio_duration_seconds=8)
        encoded = json.dumps(plan)
        with patch("persistent_store._request", return_value=[{
            "payload": payload, "encrypted_config": "",
        }]) as reader, patch("persistent_store.save_user") as saver:
            save_cloud_video_checkpoint(self.snapshot, encoded, "completed")
        saved = saver.call_args.args[2]
        self.assertEqual(saved["workspaces"][self.sid]["video_job_state"], "completed")
        others = [v for k,v in saved["workspaces"].items() if k != self.sid]
        self.assertEqual(others[0]["translated"], "preserved")
        self.assertEqual(reader.call_args.kwargs["params"]["user_id"], "eq."+uid)

    def test_cloud_checkpoint_rejects_mismatched_run_id(self):
        import time
        from cryptography.fernet import Fernet
        self.snapshot["cloud"] = {
            "secrets": {
                "SUPABASE_URL":"https://example.supabase.co",
                "SUPABASE_ANON_KEY":"public",
                "SESSION_ENCRYPTION_KEY":Fernet.generate_key().decode(),
            },
            "auth":{
                "user_id":str(uuid.uuid4()), "access_token":"jwt",
                "expires_at":time.time()+900,
            },
        }
        with patch("persistent_store._request", return_value=[{
            "payload":{"workspaces":{self.sid:{"video_job_run_id":"another"}}},
            "encrypted_config":"",
        }]), patch("persistent_store.save_user") as saver:
            with self.assertRaisesRegex(RuntimeError, "thay thế"):
                save_cloud_video_checkpoint(self.snapshot, '{"scenes":[]}', "running")
            saver.assert_not_called()


if __name__ == "__main__":
    unittest.main()

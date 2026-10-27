import json
import unittest
from unittest.mock import patch
from video_character_profiles import prepare_video_profiles
from server_video_jobs import run_video_forms_job
from background_jobs import JobProgress

class AutomaticProfilesTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {"translated": "Lan về nhà.", "language": "Vietnamese", "style": "film"}
        self.profile = {"characters": [{"name": "Lan", "reference_prompt": "Lan in blue"}], "character_bible": "Lan in blue"}

    def test_cache_and_changed_source(self):
        updates = {}
        with patch("video_character_profiles.build_character_profiles", return_value=self.profile.copy()) as build:
            result = prepare_video_profiles(self.snapshot, None, updates.__setitem__, lambda _: None)
            self.snapshot["character_profile_json"] = json.dumps(result)
            prepare_video_profiles(self.snapshot, None, updates.__setitem__, lambda _: None)
            self.assertEqual(build.call_count, 1)
            self.snapshot["translated"] += " Bà Thu chờ."
            prepare_video_profiles(self.snapshot, None, updates.__setitem__, lambda _: None)
            self.assertEqual(build.call_count, 2)
        self.assertIn("character_profile_json", updates)

    def test_partial_resume_keeps_original_name_seed(self):
        updates = {}
        state = {"sheets": [{"name": "Lan"}], "scanned": 1}
        def interrupted(*args, **kw):
            kw["checkpoint"](state)
            raise ValueError("interrupted")
        with patch("video_character_profiles.build_character_profiles", side_effect=interrupted):
            with self.assertRaises(ValueError):
                prepare_video_profiles(self.snapshot, None, updates.__setitem__, lambda _: None)
        self.snapshot.update(updates)
        with patch("video_character_profiles.build_character_profiles", return_value=self.profile.copy()) as build:
            prepare_video_profiles(self.snapshot, None, updates.__setitem__, lambda _: None)
            self.assertEqual(build.call_args.kwargs["state"], state)
            self.assertEqual(build.call_args.kwargs["canonical_names"], [])

    def test_worker_profiles_precede_forms_and_publish(self):
        snapshot = dict(self.snapshot, auto_character_profiles=True, duration_seconds=8,
                        audio_hash="x", audio_name="voice", existing_plan=None, character_bible="Old", cloud=None)
        events = []
        def build(*args, **kwargs):
            events.append("profiles")
            return self.profile.copy()
        def ai(snap, prompt):
            events.append("forms")
            self.assertIn('"Lan"', prompt)
            return '{"scenes":[{"number":1,"visual_prompt":"Lan walks home.","transition_to_next":""}]}'
        with patch("video_character_profiles.build_character_profiles", side_effect=build), patch("server_video_jobs._provider_call", side_effect=ai):
            outcome = run_video_forms_job(snapshot, JobProgress())
        self.assertTrue(outcome["ok"], outcome["error"])
        self.assertEqual(events, ["profiles", "forms"])
        self.assertEqual(json.loads(outcome["fields"]["character_profile_json"])["characters"][0]["name"], "Lan")
        self.assertEqual(json.loads(outcome["fields"]["video_forms"])["canonical_character_names"], ["Lan"])

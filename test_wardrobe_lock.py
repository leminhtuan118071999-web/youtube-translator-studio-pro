import json
import unittest
from wardrobe_lock import apply_wardrobe_lock, wardrobe_instruction
from video_scene_planner import batch_prompt
from persistent_store import normalize_sessions

class WardrobeLockTests(unittest.TestCase):
    def test_resolve_once_resume_and_prompt(self):
        plan = {"character_bible": "Lan", "language": "Vietnamese", "scenes": []}
        settings = {"wardrobe_lock_enabled": True, "wardrobe_lock_notes": "Lan: áo xanh"}
        calls = []
        def call(prompt):
            calls.append(prompt)
            return json.dumps({"wardrobe_reference": "Lan: blue blouse, black trousers."})
        apply_wardrobe_lock(plan, settings, call)
        resumed = json.loads(json.dumps(plan))
        apply_wardrobe_lock(resumed, settings, call)
        self.assertEqual(len(calls), 1)
        self.assertIn("Lan: blue blouse", batch_prompt(resumed, [], style="cinematic"))
        self.assertIn("BOTH visual_prompt and image_prompt", wardrobe_instruction(resumed))

    def test_changed_lock_clears_old_outputs_preserves_voice(self):
        plan = {"wardrobe_settings": {"enabled": True, "notes": "red"},
                "wardrobe_reference": "red", "scenes": [{"voiceover": "Hello", "visual_prompt": "red", "image_prompt": "red"}]}
        apply_wardrobe_lock(plan, {"wardrobe_lock_enabled": True, "wardrobe_lock_notes": "blue"},
                           lambda _: '{"wardrobe_reference":"blue"}')
        self.assertEqual(plan["scenes"], [{"voiceover": "Hello"}])
        self.assertEqual(plan["wardrobe_reference"], "blue")

    def test_disabled_survives_persistence(self):
        sid = "a" * 32
        result = normalize_sessions({"workspaces": {sid: {"wardrobe_lock_enabled": False, "wardrobe_lock_notes": "Lan: blue"}}})
        self.assertIs(result["workspaces"][sid]["wardrobe_lock_enabled"], False)
        self.assertEqual(result["workspaces"][sid]["wardrobe_lock_notes"], "Lan: blue")

    def test_empty_reference_rejected(self):
        with self.assertRaises(ValueError):
            apply_wardrobe_lock({"scenes": []}, {"wardrobe_lock_enabled": True}, lambda _: '{"wardrobe_reference":""}')

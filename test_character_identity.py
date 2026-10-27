import unittest
from character_identity import profile_names, apply_name_lock, name_contract, validate_speaker_spelling
from video_scene_planner import batch_prompt

class CharacterIdentityTests(unittest.TestCase):
    def test_extract_only_profile_names(self):
        self.assertEqual(profile_names('{"characters":[{"name":"Quỳnh Anh"},{"name":"Bà Thu"}],"_profile_job":{"name":"job"}}'), ["Quỳnh Anh", "Bà Thu"])
        self.assertEqual(profile_names('invalid'), [])

    def test_changed_names_invalidate_forms_and_wardrobe_only(self):
        plan = {"canonical_character_names": ["Anh"], "wardrobe_reference": "Anh: red",
                "scenes": [{"number": 1, "voiceover": "Bà ơi!", "subtitle": "Bà ơi!", "visual_prompt": "Anh", "image_prompt": "Anh"}]}
        apply_name_lock(plan, ["Quỳnh Anh"])
        self.assertNotIn("visual_prompt", plan["scenes"][0])
        self.assertNotIn("wardrobe_reference", plan)
        self.assertEqual(plan["scenes"][0]["voiceover"], "Bà ơi!")
        plan["scenes"][0]["visual_prompt"] = "Quỳnh Anh"
        apply_name_lock(plan, ["Quỳnh Anh"])
        self.assertEqual(plan["scenes"][0]["visual_prompt"], "Quỳnh Anh")

    def test_contract_in_every_batch(self):
        plan = {"language": "Vietnamese", "character_bible": "Reference", "scenes": [], "canonical_character_names": ["Bà Thu"]}
        self.assertIn(name_contract(["Bà Thu"]), batch_prompt(plan, [], style="film"))

    def test_speaker_exact_spelling_without_changing_dialogue(self):
        rows = [{"speech_segments": [{"kind": "character", "speaker": "bà thu", "text": "Thu ơi!"}]}]
        with self.assertRaises(ValueError):
            validate_speaker_spelling(rows, ["Bà Thu"])
        self.assertEqual(rows[0]["speech_segments"][0]["text"], "Thu ơi!")
        rows[0]["speech_segments"][0]["speaker"] = "Bà Thu"
        validate_speaker_spelling(rows, ["Bà Thu"])

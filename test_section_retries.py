import unittest

from section_retries import (
    rerun_translation, rerun_seo, portrait_retry_specs,
)


class IndependentSectionRetryTests(unittest.TestCase):
    def test_translation_uses_optimized_script_and_preserves_other_sections(self):
        session = {
            "source": "Very long raw transcript", "optimized_script": "Accurate condensed script",
            "translated": "Old translation", "video_forms": '{"scenes":[{"visual_prompt":"old"}]}',
            "new_title": "Old title", "new_description": "Old desc", "seo_tags": "Old tags",
            "character_bible": "Ala: red jacket with black hair.",
        }
        received = []
        def translator(text, lang):
            received.append((text,lang))
            return "New target-language translation"
        rerun_translation(session, "Tiếng Anh", translator)
        self.assertEqual(received, [("Accurate condensed script", "Tiếng Anh")])
        self.assertEqual(session["translated"], "New target-language translation")
        self.assertEqual(session["new_title"], "Old title")
        self.assertIn("old", session["video_forms"])
        self.assertTrue(session["seo_stale"])
        self.assertTrue(session["character_bible_stale"])

    def test_translation_error_cannot_erase_existing_result(self):
        session = {"optimized_script": "source", "translated": "Good translation"}
        with self.assertRaises(ValueError):
            rerun_translation(session, "English", lambda *_: "  ")
        self.assertEqual(session["translated"], "Good translation")

    def test_seo_only_commits_on_complete_result(self):
        session = {
            "translated": "Correct translation", "source": "Raw original",
            "new_title": "Old title", "new_description": "Old description",
            "seo_tags": "old", "seo_stale": True,
            "video_forms": "Existing video",
        }
        with self.assertRaises(ValueError):
            rerun_seo(session, "Tiếng Anh", lambda *_: ("new title", "", "new tags"))
        self.assertEqual(session["new_title"], "Old title")
        rerun_seo(
            session, "Tiếng Anh",
            lambda text,title,desc,lang: ("New title", "New description", "New tags"),
        )
        self.assertEqual(session["new_title"], "New title")
        self.assertEqual(session["video_forms"], "Existing video")
        self.assertFalse(session["seo_stale"])

    def test_portrait_retry_keeps_existing_character_bible(self):
        bible = "Ala: Black hair and bright red jacket.\nOla: Blond hair and vivid blue shirt."
        session = {"translated": "Ala and Ola", "character_bible": bible}
        ref, specs, changed = portrait_retry_specs(
            session, "Tiếng Anh", "2D", lambda _: self.fail("Do not call AI"),
        )
        self.assertEqual(ref,bible)
        self.assertEqual([name for name,_ in specs], ["Ala","Ola"])
        self.assertFalse(changed)

    def test_portrait_retry_can_rebuild_stale_bible(self):
        session = {
            "translated":"Ala visits the river", "character_bible":"Old characters",
            "character_bible_stale":True,
        }
        def model(prompt):
            self.assertIn("Ala visits", prompt)
            return '{"character_bible":"Ala: Black hair and long red coat.", "characters":[{"name":"Ala","description":"Black hair and long red coat"}]}'
        bible, specs, changed = portrait_retry_specs(session, "English", "2D", model)
        self.assertTrue(changed)
        self.assertEqual(specs[0][0], "Ala")
        self.assertEqual(session["character_bible"], "Old characters")


if __name__ == "__main__":
    unittest.main()

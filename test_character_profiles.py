import copy
import json
import unittest

from character_profiles import build_character_profiles, source_chunks
from character_images import CHARACTER_PROFILE_FIELDS


def scan(*names):
    return json.dumps({"world": "Khu vườn", "characters": [
        {"name": name, "evidence": "Gặp nhau trong vườn. Tóc đen."} for name in names
    ]}, ensure_ascii=False)


def sheet(name):
    return json.dumps({"characters": [{"name": name, "description": "Nhân vật trong vườn",
        **{field: "Chi tiết đề xuất tạo hình" for field, _ in CHARACTER_PROFILE_FIELDS},
        "reference_prompt": "Full body portrait, black hair, neutral backdrop."}]})


class CharacterProfileTests(unittest.TestCase):
    def test_chunks_cover_entire_source_including_middle_and_end(self):
        text = "Tấm " + "đầu " * 1800 + "Cám " + "giữa " * 1800 + "Bụt"
        chunks = source_chunks(text)
        end = 0
        for part in chunks:
            start = text.find(part, max(0, end - 200))
            self.assertLessEqual(start, end)
            self.assertGreater(start + len(part), end)
            self.assertLessEqual(len(part), 5000)
            end = start + len(part)
        self.assertEqual(end, len(text))
        self.assertTrue(any("Cám" in c for c in chunks))
        self.assertTrue(chunks[-1].endswith("Bụt"))

    def test_profiles_are_generated_one_at_a_time_with_all_later_facts(self):
        text = "Tấm " + "x " * 4000 + "Cám"
        parts = source_chunks(text)
        replies = iter([scan("Tấm", "Cám") for _ in parts] + [sheet("Tấm"), sheet("Cám")])
        prompts = []
        def call(prompt):
            prompts.append(prompt)
            return next(replies)
        result = build_character_profiles(text, "Tiếng Việt", "2D", call)
        self.assertEqual([s["name"] for s in result["characters"]], ["Tấm", "Cám"])
        self.assertEqual(len(prompts), len(parts) + 2)
        self.assertNotIn(text, prompts[-1])
        self.assertIn("SINGLE CHARACTER TASK", prompts[-1])
        self.assertIn("Tóc đen", prompts[-1])

    def test_retry_skips_scanned_source_and_completed_characters(self):
        saved = []
        replies = iter([scan("Tấm", "Cám"), sheet("Tấm")])
        def failing_call(prompt):
            try:
                return next(replies)
            except StopIteration:
                raise RuntimeError("timeout")
        with self.assertRaisesRegex(RuntimeError, "timeout"):
            build_character_profiles("Tấm gặp Cám", "vi", "2D", failing_call,
                                     checkpoint=saved.append)
        state = saved[-1]
        original = copy.deepcopy(state)
        prompts = []
        def resume(prompt):
            prompts.append(prompt)
            return sheet("Cám")
        result = build_character_profiles("Tấm gặp Cám", "vi", "2D", resume, state=state)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(len(result["characters"]), 2)
        self.assertEqual(state, original)

    def test_changed_translation_language_or_style_discards_checkpoint(self):
        saved = []
        answers = iter([scan("Tấm"), sheet("Tấm")])
        build_character_profiles("Tấm", "vi", "2D", lambda _: next(answers), checkpoint=saved.append)
        for text, language, style in (("Cám", "vi", "2D"), ("Tấm", "en", "2D"), ("Tấm", "vi", "3D")):
            with self.subTest(text=text, language=language, style=style):
                prompts = []
                answers = iter([scan("Cám"), sheet("Cám")])
                def call(prompt):
                    prompts.append(prompt)
                    return next(answers)
                result = build_character_profiles(text, language, style, call, state=saved[-1])
                self.assertEqual(len(prompts), 2)
                self.assertEqual(result["characters"][0]["name"], "Cám")

    def test_wrong_character_response_does_not_commit_sheet(self):
        saved = []
        answers = iter([scan("Tấm"), sheet("Cám")])
        with self.assertRaisesRegex(ValueError, "Tấm"):
            build_character_profiles("Tấm", "vi", "2D", lambda _: next(answers), checkpoint=saved.append)
        self.assertEqual(saved[-1]["scanned"], 1)
        self.assertEqual(saved[-1]["sheets"], [])

    def test_invalid_scan_is_not_checkpointed(self):
        saved = []
        with self.assertRaises(ValueError):
            build_character_profiles("Tấm", "vi", "2D", lambda _: '{"characters":[{"name":"Tấm"}]}',
                                     checkpoint=saved.append)
        self.assertEqual(saved, [])

    def test_streamlit_timeout_retains_old_profiles_and_resumes(self):
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file("streamlit_app.py", default_timeout=20)
        for key in ("_browser_sessions_restored", "_browser_api_restored", "_session_name_test_fallback"):
            app.session_state[key] = True
        app.session_state["api_provider"] = "OpenAI"
        app.session_state["api_key_OpenAI"] = "test-secret"
        app.run()
        self.assertFalse(app.exception)
        sid = app.session_state["selected_session"]
        session = app.session_state["workspaces"][sid]
        session["translated"] = "Tấm gặp Cám trong vườn."
        old = {"characters": [{"name": "Tấm", "hair": "Tóc đã sửa"}],
               "character_bible": "Hồ sơ cũ"}
        session["character_profile_json"] = json.dumps(old)
        session["character_bible"] = "Hồ sơ cũ"
        app.run()
        def click():
            next(x for x in app.button if x.key == f"regenerate_detailed_characters_{sid}").click().run()
        with patch("api_clients.generate_text", side_effect=[scan("Tấm", "Cám"), sheet("Tấm"), RuntimeError("timeout")]) as api:
            click()
            self.assertEqual(api.call_count, 3)
        self.assertFalse(app.exception)
        saved = json.loads(app.session_state["workspaces"][sid]["character_profile_json"])
        self.assertEqual(saved["characters"], old["characters"])
        self.assertEqual(len(saved["_profile_build"]["sheets"]), 1)
        self.assertTrue(any("timeout" in x.value for x in app.error))
        # An unrelated rerender must not discard the checkpoint.
        app.run()
        with patch("api_clients.generate_text", return_value=sheet("Cám")) as api:
            click()
            self.assertEqual(api.call_count, 1)
        self.assertFalse(app.exception)
        final = json.loads(app.session_state["workspaces"][sid]["character_profile_json"])
        self.assertNotIn("_profile_build", final)
        self.assertEqual([s["name"] for s in final["characters"]], ["Tấm", "Cám"])


if __name__ == "__main__":
    unittest.main()

"""Strict scene-language, timing and source-fidelity regression tests."""
import json
import unittest

from video_scene_planner import (
    narration_plan, source_fingerprint, character_bible_prompt,
    batch_prompt, apply_ai_batch, plan_export_text, continuous_video_forms_text,
)


class VideoScenePlannerTests(unittest.TestCase):
    def test_eight_second_scenes_keep_every_word_of_target_translation(self):
        original = " ".join(f"Polskie słowo {n}." for n in range(75))
        plan = narration_plan(original, "Tiếng Ba Lan", words_per_minute=120)
        self.assertTrue(len(plan["scenes"]) > 1)
        self.assertEqual(
            " ".join(x["voiceover"] for x in plan["scenes"]), original
        )
        self.assertTrue(all(x["duration_seconds"] == 8 for x in plan["scenes"]))
        for i, scene in enumerate(plan["scenes"]):
            self.assertEqual(scene["start_seconds"], i * 8)
            self.assertEqual(scene["end_seconds"], (i+1) * 8)
            self.assertEqual(scene["number"], i+1)
            if i < len(plan["scenes"])-1:
                self.assertIn("crossfade", scene["transition_to_next"])
            else:
                self.assertEqual(scene["transition_to_next"], "")
        self.assertEqual(
            plan["source_hash"], source_fingerprint(original, "Tiếng Ba Lan")
        )

    def test_duration_audio_changes_scene_count_and_end_padding(self):
        original = " ".join(["story"] * 150)
        no_audio = narration_plan(original, "Tiếng Anh", words_per_minute=150)
        with_audio = narration_plan(
            original, "Tiếng Anh", audio_duration_seconds=17.8
        )
        self.assertEqual(len(with_audio["scenes"]), 3)
        self.assertEqual(with_audio["end_padding_seconds"], 6.2)
        self.assertNotEqual(len(no_audio["scenes"]), len(with_audio["scenes"]))
        self.assertEqual(
            " ".join(x["voiceover"] for x in with_audio["scenes"]), original
        )

    def test_wav_voiceover_duration_reader_is_accurate(self):
        from io import BytesIO
        import wave
        from video_forms_ui import _audio_duration

        payload = BytesIO()
        with wave.open(payload, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"\\x00\\x00" * (8000 * 3))
        class Uploaded:
            def getvalue(self):
                return payload.getvalue()
        self.assertAlmostEqual(_audio_duration(Uploaded()), 3.0, places=1)

    def test_language_with_no_spaces_does_not_drop_characters(self):
        original = "こんにちは世界今日は良い天気です"
        plan = narration_plan(original, "Tiếng Nhật")
        self.assertEqual(
            "".join(x["voiceover"] for x in plan["scenes"]), original
        )

    def test_reject_mismatched_audio_and_bad_data(self):
        for audio in (float("nan"), float("inf"), 0, -5):
            with self.assertRaises(ValueError):
                narration_plan("some text", "Tiếng Anh",
                               audio_duration_seconds=audio)
        with self.assertRaises(ValueError):
            narration_plan("two words", "Tiếng Anh", audio_duration_seconds=480)
        with self.assertRaises(ValueError):
            narration_plan("", "Tiếng Anh")
        with self.assertRaises(ValueError):
            narration_plan("Hello", "")
        with self.assertRaises(ValueError):
            narration_plan("Hello", "Tiếng Anh", words_per_minute=50)

    def test_fixed_character_bible_and_ai_cannot_rewrite_narration(self):
        original = "Ala walks into the garden. Ala meets Ola."
        plan = narration_plan(original, "Tiếng Ba Lan")
        plan["style"] = "Hoạt hình 2D"
        plan["character_bible"] = (
            "Ala: czerwony płaszcz, czarne włosy. "
            "Ola: niebieska kurtka, blond włosy."
        )
        prompt = batch_prompt(plan, plan["scenes"], style=plan["style"])
        self.assertIn(plan["character_bible"], prompt)
        self.assertIn("0-8 second timeline", prompt)
        self.assertIn("0.4 second", prompt)
        self.assertIn("ONLY in Tiếng Ba Lan", prompt)
        expected = [scene["number"] for scene in plan["scenes"]]
        generated = json.dumps({
            "scenes": [
                {"number": n, "visual_prompt": f"Opis wizualny {n}",
                 "transition_to_next": "płynne przenikanie"}
                for n in expected
            ]
        })
        before = [x["voiceover"] for x in plan["scenes"]]
        apply_ai_batch(plan, generated, expected)
        self.assertEqual([x["voiceover"] for x in plan["scenes"]], before)
        self.assertTrue(all(
            x["visual_prompt"].startswith(plan["character_bible"])
            for x in plan["scenes"]
        ))
        self.assertEqual(plan["scenes"][-1]["transition_to_next"], "")
        content = plan_export_text(plan)
        self.assertIn("Voiceover:", content)
        self.assertIn("Character continuity:", content)

    def test_malformed_model_output_never_partially_changes_plan(self):
        plan = narration_plan(" ".join(["hello"] * 60), "Tiếng Anh")
        plan["style"] = "Hoạt hình 3D"
        plan["character_bible"] = "Character A"
        expected = [s["number"] for s in plan["scenes"]]
        bad = json.dumps({
            "scenes": [
                {"number": expected[0], "visual_prompt": "ok",
                 "transition_to_next": ""}
            ] * len(expected)
        })
        with self.assertRaises(ValueError):
            apply_ai_batch(plan, bad, expected)
        self.assertTrue(all(s["visual_prompt"] == "" for s in plan["scenes"]))

    def test_copy_all_forms_one_line_each_in_order(self):
        plan = narration_plan(" ".join(["story"] * 40), "Tiếng Anh")
        self.assertGreaterEqual(len(plan["scenes"]), 2)
        plan["scenes"][0]["visual_prompt"] = "A camera zoom.\\nBeautiful lighting."
        plan["scenes"][1]["visual_prompt"] = "Character walks forward."
        out = continuous_video_forms_text(plan)
        lines = out.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("FORM 001"))
        self.assertTrue(lines[1].startswith("FORM 002"))
        self.assertIn("VOICEOVER (Tiếng Anh):", lines[0])
        self.assertIn("Beautiful lighting.", lines[0])
        self.assertIn("TRANSITION:", lines[0])
        self.assertNotIn("TRANSITION:", lines[1])
        self.assertNotIn("not generated", out)

    def test_character_bible_prompt_uses_target_translation(self):
        text = "Dzisiaj Ala przyszła do domu."
        request = character_bible_prompt(text, "Tiếng Ba Lan", "Hoạt hình 2D")
        self.assertIn(text, request)
        self.assertIn("Tiếng Ba Lan", request)
        self.assertIn("consistent", request)
        self.assertNotIn("20 prompt hình ảnh", request)


if __name__ == "__main__":
    unittest.main()

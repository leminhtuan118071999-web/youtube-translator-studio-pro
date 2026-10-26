import json
import unittest
from unittest.mock import patch
from background_jobs import optimize_source_script, run_full_job, JobProgress, MAX_OPTIMIZED_SCRIPT_CHARS


class OptimizedScriptWorkflowTests(unittest.TestCase):
    def test_optimizes_before_translation_and_generates_video_automatically(self):
        transcript = "The original tale with characters, events and a conclusion."
        calls = []
        def provider(_p, _b, _m, _k, prompt):
            calls.append(prompt)
            if "Viết lại PHẦN" in prompt:
                return "A concise tale preserving the characters, events and conclusion."
            if "CHỈ xuất bản dịch" in prompt:
                self.assertIn("concise tale", prompt)
                return "Een beknopt verhaal met de personages, gebeurtenissen en afloop."
            if "CHARACTER/WORLD REFERENCE" in prompt:
                return '{"character_bible":"Een vrouw met donker haar en rode jas."}'
            if "self-contained scene-generation prompts" in prompt:
                batch=json.loads(prompt.split("Input scenes:\n",1)[1])
                return json.dumps({"scenes":[
                    {"number":x["number"],"visual_prompt":"Een levendige scène.",
                     "transition_to_next":"zachte overgang"} for x in batch
                ]})
            if "Soạn YouTube tiêu đề" in prompt:
                return '{"title":"Een titel","description":"Een beschrijving","tags":["tag"]}'
            self.fail("Unexpected provider request " + prompt[:80])
        cfg={"source":transcript,"url":"","title":"Original","description":"",
             "language":"Tiếng Hà Lan","provider":"Groq",
             "base_url":"https://api.groq.com/openai/v1","model":"test",
             "api_key":"KEY-SECRET","auto_video_forms":True}
        with patch("background_jobs.generate_text", side_effect=provider),patch(
            "background_jobs.optimize_source_script",wraps=optimize_source_script
        ):
            result=run_full_job(cfg,JobProgress())
        self.assertTrue(result["ok"],result["error"])
        self.assertLess(len(result["fields"]["optimized_script"]),10000)
        self.assertIn("beknopt",result["fields"]["translated"])
        plan=json.loads(result["fields"]["video_forms"])
        self.assertEqual(plan["language"],"Tiếng Hà Lan")
        self.assertEqual(plan["seconds_per_scene"],8)
        self.assertTrue(plan["scenes"][0]["visual_prompt"])
        self.assertLess(
            next(i for i,p in enumerate(calls) if "Viết lại PHẦN" in p),
            next(i for i,p in enumerate(calls) if "CHỈ xuất bản dịch" in p),
        )
        self.assertLess(
            next(i for i,p in enumerate(calls) if "CHỈ xuất bản dịch" in p),
            next(i for i,p in enumerate(calls) if "CHARACTER/WORLD REFERENCE" in p),
        )

    def test_automatically_generates_session_scoped_portraits_after_bible(self):
        from character_images import IMAGE_STORE
        source = "The hero Ala meets Ola at the lake."
        calls = []
        def provider(_p, _b, _m, _k, prompt):
            calls.append(prompt)
            if "CHỈ xuất bản dịch" in prompt:
                return "Ala meets Ola in the lake."
            if "CHARACTER/WORLD REFERENCE" in prompt:
                return json.dumps({
                    "character_bible": "Ala in red. Ola in blue.",
                    "characters": [
                        {"name": "Ala", "description": "Red coat, dark hair"},
                        {"name": "Ola", "description": "Blue jacket, light hair"},
                    ],
                })
            if "self-contained scene-generation prompts" in prompt:
                batch = json.loads(prompt.split("Input scenes:\\n", 1)[1])
                return json.dumps({"scenes": [
                    {"number": row["number"], "visual_prompt": "A lake scene",
                     "transition_to_next": "crossfade"}
                    for row in batch
                ]})
            if "Soạn YouTube tiêu đề" in prompt:
                return '{"title":"Title","description":"Description","tags":["tag"]}'
            self.fail("Unexpected prompt")
        config = {
            "source": source, "url": "", "language": "Tiếng Anh",
            "provider": "Groq", "base_url": "https://api.groq.com/openai/v1",
            "model": "test", "api_key": "translation-secret",
            "auto_video_forms": True, "auto_character_images": True,
            "image_api_key": "image-secret", "image_scope": "account:owner",
            "image_session_id": "a" * 32,
        }
        with patch("background_jobs.optimize_source_script", return_value=source), patch(
            "background_jobs.generate_text", side_effect=provider
        ), patch(
            "background_jobs.create_character_png", return_value=b"PNG_BYTES"
        ) as images:
            try:
                result = run_full_job(config, JobProgress())
                self.assertTrue(result["ok"], result["error"])
                self.assertEqual(images.call_count, 2)
                self.assertEqual(result["fields"]["character_images_count"], 2)
                self.assertEqual(
                    list(IMAGE_STORE.images("account:owner", "a" * 32)),
                    ["Ala", "Ola"],
                )
                self.assertIn("video_forms", result["fields"])
                self.assertNotIn("PNG_BYTES", repr(result))
                self.assertNotIn("image-secret", repr(result))
                self.assertLess(
                    next(i for i, prompt in enumerate(calls)
                         if "CHARACTER/WORLD REFERENCE" in prompt),
                    next(i for i, prompt in enumerate(calls)
                         if "self-contained scene-generation prompts" in prompt),
                )
            finally:
                IMAGE_STORE.clear("account:owner", "a" * 32)

    def test_unsuccessful_video_generation_does_not_discard_translation_or_seo(self):
        def provider(_p,_b,_m,_k,prompt):
            if "CHỈ xuất bản dịch" in prompt:return "Translated text."
            if "CHARACTER/WORLD REFERENCE" in prompt:raise RuntimeError("Video form unavailable")
            if "Soạn YouTube tiêu đề" in prompt:
                return '{"title":"Title","description":"Description","tags":["tag"]}'
            self.fail("Unexpected prompt")
        cfg={"source":"An original narrative.","url":"","language":"Tiếng Anh",
             "provider":"Groq","base_url":"https://api.groq.com/openai/v1",
             "model":"test","api_key":"KEY-SECRET","auto_video_forms":True}
        with patch("background_jobs.optimize_source_script",return_value="An optimized narrative."),patch(
            "background_jobs.generate_text",side_effect=provider
        ):
            result=run_full_job(cfg,JobProgress())
        self.assertTrue(result["ok"],result["error"])
        self.assertEqual(result["fields"]["translated"],"Translated text.")
        self.assertIn("Video form unavailable",result["fields"]["video_forms_error"])
        self.assertEqual(result["fields"]["new_title"],"Title")

    def test_unable_to_reduce_under_10000_never_silently_truncates_story(self):
        huge=("A long story with details and ending. " * 600)
        def stubborn(_prompt):
            return "x" * 11000
        with self.assertRaisesRegex(ValueError,"10.000"):
            optimize_source_script(huge,stubborn,JobProgress())
        self.assertEqual(MAX_OPTIMIZED_SCRIPT_CHARS,9999)


if __name__=="__main__":
    unittest.main()

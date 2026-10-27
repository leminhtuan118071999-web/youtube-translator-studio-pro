from test_selection_helpers import whole_source_selection
import json
import unittest
from unittest.mock import patch
from background_jobs import optimize_source_script, run_full_job, JobProgress, MAX_OPTIMIZED_SCRIPT_CHARS


class OptimizedScriptWorkflowTests(unittest.TestCase):
    def test_rewrites_original_directly_and_keeps_seo_without_auto_video(self):
        transcript = "The original tale with characters, events and a conclusion."
        calls = []
        def provider(_p, _b, _m, _k, prompt):
            if prompt.startswith("STORY_ARC_SELECTION"):
                return whole_source_selection(prompt)
            calls.append(prompt)
            if prompt.startswith("STORY_REPAIR_PLAN"):
                return '{"edits":[],"unresolved":[]}'
            if prompt.startswith("FAITHFULNESS_REVIEW"):
                return '{"ok":true,"issues":[],"source_conflicts":[]}'
            if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
                return json.dumps({"summary":"Een beknopt verhaal met de personages, gebeurtenissen en afloop.",
                    "entities":[],"edits":[],"unresolved":[],
                    "anchors":[{"fact":"Original tale","quote":transcript}]})
            if "CHỈ xuất bản dịch" in prompt:
                self.assertIn("original tale", prompt)
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
             "api_key":"KEY-SECRET","auto_video_forms":False}
        with patch("background_jobs.generate_text", side_effect=provider):
            result=run_full_job(cfg,JobProgress())
        self.assertTrue(result["ok"],result["error"])
        self.assertLess(len(result["fields"]["optimized_script"]),10000)
        self.assertIn("beknopt",result["fields"]["translated"])
        self.assertNotIn("video_forms", result["fields"])
        self.assertEqual(result["fields"]["optimized_script"], result["fields"]["translated"])
        self.assertEqual(result["fields"]["source"], transcript)
        self.assertTrue(any("TARGET_STORY_REWRITE" in p for p in calls))
        self.assertFalse(any("CHỈ xuất bản dịch" in p for p in calls))
        self.assertTrue(any(p.startswith("FAITHFULNESS_REVIEW") for p in calls))
        self.assertTrue(any("CHARACTER/WORLD REFERENCE" in p for p in calls))
        # Character profile creation is now a standard text stage, even
        # when image generation is not configured. Video forms still wait
        # for the separately uploaded completed narration audio.
        self.assertFalse(any("self-contained scene-generation prompts" in p for p in calls))
        self.assertEqual(result["fields"]["new_title"], "Een titel")

    def test_automatically_generates_session_scoped_portraits_after_bible(self):
        from character_images import IMAGE_STORE
        source = "The hero Ala meets Ola at the lake."
        calls = []
        def provider(_p, _b, _m, _k, prompt):
            if prompt.startswith("STORY_ARC_SELECTION"):
                return whole_source_selection(prompt)
            calls.append(prompt)
            if prompt.startswith("STORY_REPAIR_PLAN"):
                return '{"edits":[],"unresolved":[]}'
            if prompt.startswith("FAITHFULNESS_REVIEW"):
                return '{"ok":true,"issues":[],"source_conflicts":[]}'
            if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
                return json.dumps({"summary":"Ala meets Ola in the lake.","entities":[],"edits":[],"unresolved":[],
                    "anchors":[{"fact":"Meeting","quote":source}]})
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
            "auto_video_forms": False, "auto_character_images": True,
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
                self.assertNotIn("video_forms", result["fields"])
                self.assertIn("character_bible", result["fields"])
                self.assertNotIn("PNG_BYTES", repr(result))
                self.assertNotIn("image-secret", repr(result))
                self.assertTrue(any("CHARACTER/WORLD REFERENCE" in prompt for prompt in calls))
                self.assertFalse(any("self-contained scene-generation prompts" in prompt for prompt in calls))
            finally:
                IMAGE_STORE.clear("account:owner", "a" * 32)

    def test_unable_to_reduce_under_10000_never_silently_truncates_story(self):
        huge=("A long story with details and ending. " * 600)
        def stubborn(_prompt):
            if _prompt.startswith("STORY_REPAIR_PLAN"):
                return '{"edits":[],"unresolved":[]}'
            return "x" * 11000
        with self.assertRaisesRegex(ValueError,"10.000"):
            optimize_source_script(huge,stubborn,JobProgress())
        self.assertEqual(MAX_OPTIMIZED_SCRIPT_CHARS,9999)


if __name__=="__main__":
    unittest.main()

import json
import unittest
from unittest.mock import patch

from background_jobs import JobProgress, run_full_job, chunk_text, youtube_id


class BackgroundJobsTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "url": "https://youtube.com/watch?v=12345678901",
            "source": "",
            "title": "Original title",
            "description": "Original description",
            "language": "Tiếng Ba Lan",
            "provider": "Groq",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "openai/gpt-oss-120b",
            "api_key": "SECRET-KEY-123",
        }

    def test_video_id_parsing(self):
        self.assertEqual(youtube_id(self.config["url"]), "12345678901")
        self.assertIsNone(youtube_id("not a video url"))

    def test_chunking_preserves_characters(self):
        text = "This is a test sentence. " * 100
        self.assertEqual("".join(chunk_text(text, 55)), text)

    @patch("background_jobs.fetch_subtitles", return_value=("Original subtitle content.", "English"))
    @patch("background_jobs.generate_text")
    def test_completed_video_uses_snapshot_and_returns_all_fields(self, api, subs):
        def mock_ai(provider, base_url, model, api_key, prompt):
            self.assertEqual(api_key, self.config["api_key"])
            if "CHỈ xuất bản dịch" in prompt:
                return "Treść przetłumaczona na język polski."
            if "ĐÚNG 20 prompt" in prompt:
                return json.dumps({"prompts": ["Obraz " + str(i) for i in range(20)]})
            if "Soạn YouTube tiêu đề" in prompt:
                return json.dumps({"title": "Tytuł", "description": "Opis", "tags": ["tag-a","tag-b"]})
            self.fail("Unexpected prompt: " + prompt[:100])
        api.side_effect = mock_ai
        progress = JobProgress()
        result = run_full_job(self.config.copy(), progress)
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["fields"]["source"], "Original subtitle content.")
        self.assertEqual(result["fields"]["new_title"], "Tytuł")
        self.assertEqual(result["fields"]["new_description"], "Opis")
        self.assertEqual(result["fields"]["seo_tags"], "tag-a, tag-b")
        self.assertEqual(len(json.loads(result["fields"]["prompts"])), 20)
        self.assertEqual(progress.snapshot()[0], 100)
        self.assertNotIn("api_key", result["fields"])
        self.assertNotIn(self.config["api_key"], repr(result))

    @patch("background_jobs.fetch_subtitles", return_value=("Original subtitle.", "English"))
    @patch("background_jobs.generate_text")
    def test_partial_work_kept_when_prompts_fail(self, api, subs):
        def mock_ai(_provider, _url, _model, _key, prompt):
            if "CHỈ xuất bản dịch" in prompt:
                return "Przetłumaczony tekst."
            return '{"prompts": ["only one scene"]}'
        api.side_effect = mock_ai
        result = run_full_job(self.config.copy(), JobProgress())
        self.assertFalse(result["ok"])
        self.assertIn("translated", result["fields"])
        self.assertNotIn("prompts", result["fields"])
        self.assertIn("20", result["error"])

    @patch("background_jobs.fetch_subtitles", return_value=("Subtitle from video.", "English"))
    @patch("background_jobs.generate_text")
    def test_live_checkpoints_available_before_job_finishes(self, api, subs):
        def mock_ai(_provider, _url, _model, _key, prompt):
            if "CHỈ xuất bản dịch" in prompt:
                return "Przetłumaczony tekst"
            if "ĐÚNG 20 prompt" in prompt:
                return '{"prompts":["one scene only"]}'
            self.fail("Unexpected prompt")
        api.side_effect = mock_ai
        progress = JobProgress()
        response = run_full_job(self.config.copy(), progress)
        self.assertFalse(response["ok"])
        live = progress.partial_result()
        self.assertEqual(live["source"], "Subtitle from video.")
        self.assertEqual(live["translated"], "Przetłumaczony tekst")
        self.assertNotIn("api_key", live)
        self.assertNotIn(self.config["api_key"], repr(live))

    def test_progress_snapshot_isolated_copy(self):
        progress = JobProgress()
        progress.publish("translated", "First part")
        snapshot = progress.partial_result()
        snapshot["translated"] = "not same as internal"
        self.assertEqual(progress.partial_result()["translated"], "First part")

    def test_cancel_does_not_touch_provider(self):
        progress = JobProgress()
        progress.cancel()
        result = run_full_job(self.config.copy(), progress)
        self.assertFalse(result["ok"])
        self.assertIn("hủy", result["error"])

    @patch("background_jobs.fetch_subtitles", side_effect=RuntimeError("SECRET-KEY-123 leaked"))
    def test_provider_key_redacted_from_failures(self, subs):
        result = run_full_job(self.config.copy(), JobProgress())
        self.assertFalse(result["ok"])
        self.assertNotIn(self.config["api_key"], repr(result))


if __name__ == "__main__":
    unittest.main()

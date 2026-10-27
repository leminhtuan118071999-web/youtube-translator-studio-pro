import json
import unittest
from unittest.mock import patch

from background_jobs import JobProgress, run_full_job, chunk_text, youtube_id, overview
from api_clients import RateLimitError, TransientProviderError


class BackgroundJobsTests(unittest.TestCase):
    def setUp(self):
        # Isolate API retry/pacing tests from source-to-target drafting/review.
        def rewrite(source, language, call, progress):
            return "\n\n".join(call(
                f"Dịch sang {language}. CHỈ xuất bản dịch.\n\n" + part
            ) for part in chunk_text(source, 2200))
        worker = patch("background_jobs.rewrite_target_script", side_effect=rewrite)
        worker.start()
        self.addCleanup(worker.stop)
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
    def test_completed_video_generates_translation_and_seo_without_image_prompts(self, api, subs):
        def mock_ai(provider, base_url, model, api_key, prompt):
            self.assertEqual(api_key, self.config["api_key"])
            if "CHỈ xuất bản dịch" in prompt:
                return "Treść przetłumaczona na język polski."
            if "CHARACTER/WORLD REFERENCE" in prompt:
                return json.dumps({
                    "character_bible": "Nhân vật được nhận diện theo bản dịch.",
                    "characters": [{
                        "name": "Ala", "description": "Young woman with a red coat",
                        "face": "Oval face", "hair": "Dark hair",
                        "outfit": "Fixed red coat", "palette": "Red and brown",
                        "source_notes": "Colors proposed for visual consistency",
                        "reference_prompt": "Full-body character sheet",
                    }],
                })
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
        self.assertNotIn("prompts", result["fields"])
        self.assertEqual(api.call_count, 3)  # Translation + character profiles + SEO
        self.assertEqual(progress.snapshot()[0], 100)
        self.assertNotIn("api_key", result["fields"])
        self.assertNotIn(self.config["api_key"], repr(result))

    @patch("background_jobs.fetch_subtitles", return_value=("Original subtitle.", "English"))
    @patch("background_jobs.generate_text")
    def test_partial_work_kept_when_seo_fails(self, api, subs):
        def mock_ai(_provider, _url, _model, _key, prompt):
            if "CHỈ xuất bản dịch" in prompt:
                return "Przetłumaczony tekst."
            raise RuntimeError("SEO request failed")
        api.side_effect = mock_ai
        result = run_full_job(self.config.copy(), JobProgress())
        self.assertFalse(result["ok"])
        self.assertIn("translated", result["fields"])
        self.assertNotIn("prompts", result["fields"])
        self.assertIn("SEO request failed", result["error"])

    @patch("background_jobs.fetch_subtitles", return_value=("Subtitle from video.", "English"))
    @patch("background_jobs.generate_text")
    def test_live_checkpoints_available_before_job_finishes(self, api, subs):
        def mock_ai(_provider, _url, _model, _key, prompt):
            if "CHỈ xuất bản dịch" in prompt:
                return "Przetłumaczony tekst"
            raise RuntimeError("SEO unavailable")
        api.side_effect = mock_ai
        progress = JobProgress()
        response = run_full_job(self.config.copy(), progress)
        self.assertFalse(response["ok"])
        live = progress.partial_result()
        self.assertEqual(live["source"], "Subtitle from video.")
        self.assertEqual(live["translated"], "Przetłumaczony tekst")
        self.assertNotIn("prompts", live)
        self.assertNotIn("api_key", live)
        self.assertNotIn(self.config["api_key"], repr(live))

    def test_progress_snapshot_isolated_copy(self):
        progress = JobProgress()
        progress.publish("translated", "First part")
        snapshot = progress.partial_result()
        snapshot["translated"] = "not same as internal"
        self.assertEqual(progress.partial_result()["translated"], "First part")

    @patch("background_jobs.fetch_subtitles")
    @patch("background_jobs.generate_text")
    def test_uploaded_subtitles_bypass_blocked_youtube(self, api, download):
        def mock_ai(_provider, _url, _model, _key, prompt):
            if "CHỈ xuất bản dịch" in prompt:
                return "Przetłumaczony tekst."
            if "Soạn YouTube tiêu đề" in prompt:
                return json.dumps({"title":"Tytuł","description":"Opis","tags":["a","b"]})
            self.fail("Unexpected text request")
        api.side_effect = mock_ai
        config = self.config.copy()
        config["uploaded_source"] = "Subtitle supplied by user"
        config["supadata_key"] = ""
        result = run_full_job(config, JobProgress())
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["fields"]["source"], "Subtitle supplied by user")
        download.assert_not_called()

    @patch("background_jobs.fetch_subtitles", side_effect=RuntimeError("Supadata SupaKeyBroken"))
    def test_supadata_credentials_are_redacted_from_error(self, download):
        config = self.config.copy()
        config["supadata_key"] = "SupaKeyBroken"
        result = run_full_job(config, JobProgress())
        self.assertFalse(result["ok"])
        self.assertNotIn("SupaKeyBroken", result["error"])

    @patch("background_jobs.time.sleep", return_value=None)
    @patch("background_jobs.fetch_subtitles", return_value=("A complete transcript.", "English"))
    @patch("background_jobs.generate_text")
    def test_429_retries_failed_translation_without_redoing_completed_work(self, api, subs, sleep):
        calls = {"translate": 0}
        def fake_api(provider, base_url, model, api_key, prompt):
            if "CHỈ xuất bản dịch" in prompt:
                calls["translate"] += 1
                if calls["translate"] == 1:
                    raise RateLimitError("Too many tokens", retry_after=2)
                return "Tłumaczenie."
            if "Soạn YouTube tiêu đề" in prompt:
                return json.dumps({"title":"Tytuł","description":"Opis","tags":["tag1","tag2"]})
            self.fail("Unexpected query")
        api.side_effect = fake_api
        progress = JobProgress()
        result = run_full_job(self.config.copy(), progress)
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(calls["translate"], 2)
        self.assertIn("Tłumaczenie", result["fields"]["translated"])
        self.assertGreaterEqual(sleep.call_count, 1)

    @patch("background_jobs.time.sleep", return_value=None)
    @patch("background_jobs.fetch_subtitles", return_value=("A transcript.", "English"))
    @patch("background_jobs.generate_text", side_effect=RateLimitError("TPM limit", retry_after=1))
    def test_exhausted_retry_budget_preserves_source(self, api, subs, sleep):
        progress = JobProgress()
        result = run_full_job(self.config.copy(), progress)
        self.assertFalse(result["ok"])
        self.assertIn("6 lần", result["error"])
        self.assertEqual(api.call_count, 7)
        self.assertIn("source", result["fields"])
        self.assertNotIn("translated", result["fields"])

    @patch("background_jobs.fetch_subtitles", return_value=("A transcript.", "English"))
    @patch("background_jobs.generate_text", side_effect=RateLimitError("TPD limit", retry_after=60, can_retry=False))
    def test_daily_quota_not_retried(self, api, subs):
        result = run_full_job(self.config.copy(), JobProgress())
        self.assertFalse(result["ok"])
        self.assertEqual(api.call_count, 1)
        self.assertIn("ngày", result["error"])

    @patch("background_jobs.fetch_subtitles")
    @patch("background_jobs.generate_text")
    def test_groq_translation_is_split_into_small_chunks(self, api, subs):
        content = "Story. " * 1800
        subs.return_value = (content, "English")
        prompt_lengths = []
        def fake_ai(_provider, _url, _model, _key, prompt):
            if "CHỈ xuất bản dịch" in prompt:
                prompt_lengths.append(len(prompt))
                return "Translation."
            if "Soạn YouTube tiêu đề" in prompt:
                return json.dumps({"title":"Title","description":"Description","tags":["tag1"]})
            if "Summarize" in prompt or "Condense" in prompt:
                return "Brief scene events."
            self.fail("Unexpected prompt")
        api.side_effect = fake_ai
        result = run_full_job(self.config.copy(), JobProgress())
        self.assertTrue(result["ok"], result["error"])
        self.assertGreater(len(prompt_lengths), 3)
        self.assertLessEqual(max(prompt_lengths), 2600)

    @patch("background_jobs.fetch_subtitles")
    @patch("background_jobs.generate_text")
    def test_split_translation_reassembles_all_chunks_in_order(self, ai, subs):
        text = "This is a separate sentence for a longer video. " * 180
        subs.return_value = (text, "English")
        seen_chunks = []
        def respond(_provider, _base, _model, _token, prompt):
            if "CHỈ xuất bản dịch" in prompt:
                index = len(seen_chunks) + 1
                seen_chunks.append(prompt)
                return f"Bản dịch phần {index}"
            if "Soạn YouTube tiêu đề" in prompt:
                return json.dumps({"title": "Title", "description": "Description", "tags": ["tag"]})
            if "Summarize" in prompt or "Condense" in prompt:
                return "Short summary of the whole story."
            self.fail("Unexpected prompt")
        ai.side_effect = respond
        result = run_full_job(self.config.copy(), JobProgress())
        self.assertTrue(result["ok"], result["error"])
        self.assertGreater(len(seen_chunks), 2)
        self.assertEqual(
            result["fields"]["translated"],
            "\\n\\n".join(
                f"Bản dịch phần {idx}" for idx in range(1, len(seen_chunks) + 1)
            ).replace("\\n", "\n")
        )
        # Groq never sends more than 2,200 source characters in one chunk.
        self.assertTrue(all(len(prompt) < 2500 for prompt in seen_chunks))

    @patch("background_jobs.time.sleep", return_value=None)
    @patch("background_jobs.fetch_subtitles",
           return_value=("A short real subtitle for translating.", "English"))
    @patch("background_jobs.generate_text")
    def test_gateway_502_retries_and_recovers_without_repeating_chunks(
        self, api, subs, sleep
    ):
        config = {**self.config, "provider": "Claude Gateway (AUTH_TOKEN)"}
        calls = {"translation": 0}
        def server(_provider, _url, _model, _key, prompt):
            if "CHỈ xuất bản dịch" in prompt:
                calls["translation"] += 1
                if calls["translation"] == 1:
                    raise TransientProviderError(
                        "HTTP 502: Upstream service temporarily unavailable",
                        status_code=502, retry_after=2
                    )
                return "Translation done"
            if "Soạn YouTube tiêu đề" in prompt:
                return json.dumps({
                    "title": "Title", "description": "Description", "tags": ["tag"]
                })
            self.fail("Unexpected request")
        api.side_effect = server
        result = run_full_job(config, JobProgress())
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(calls["translation"], 2)
        self.assertEqual(result["fields"]["translated"], "Translation done")
        self.assertGreater(sleep.call_count, 0)

    @patch("background_jobs.time.sleep", return_value=None)
    @patch("background_jobs.fetch_subtitles", return_value=("A short subtitle.", "English"))
    @patch("background_jobs.generate_text")
    def test_gateway_502_exhausts_three_retries_and_keeps_partial_source(
        self, api, subs, sleep
    ):
        config = {**self.config, "provider": "Claude Gateway (AUTH_TOKEN)"}
        api.side_effect = TransientProviderError(
            "HTTP 502: upstream unavailable", status_code=502, retry_after=2
        )
        result = run_full_job(config, JobProgress())
        self.assertFalse(result["ok"])
        self.assertEqual(api.call_count, 4)
        self.assertIn("502", result["error"])
        self.assertIn("3 lần", result["error"])
        self.assertEqual(result["fields"]["source"], "A short subtitle.")
        self.assertNotIn("translated", result["fields"])

    @patch("background_jobs.time.sleep", return_value=None)
    @patch("background_jobs.fetch_subtitles", return_value=("A short subtitle.", "English"))
    @patch("background_jobs.generate_text")
    def test_gateway_401_does_not_retry(self, api, subs, sleep):
        config = {**self.config, "provider": "Claude Gateway (AUTH_TOKEN)"}
        api.side_effect = RuntimeError("HTTP 401: Invalid token")
        result = run_full_job(config, JobProgress())
        self.assertFalse(result["ok"])
        self.assertIn("HTTP 401", result["error"])
        api.assert_called_once()
        sleep.assert_not_called()

    @patch("background_jobs.fetch_subtitles", return_value=("A short subtitle.", "English"))
    @patch("background_jobs.generate_text")
    def test_third_party_api_options_reach_all_background_requests(self, api, subs):
        config = {
            **self.config,
            "provider": "API bên thứ ba (tùy chỉnh)",
            "base_url": "https://example.net/v1",
            "model": "third-party-model",
            "api_format": "anthropic",
            "auth_mode": "api_key",
        }
        def respond(_provider, _url, _model, _key, prompt, **kwargs):
            self.assertEqual(_provider, "API bên thứ ba (tùy chỉnh)")
            self.assertEqual(_url, "https://example.net/v1")
            self.assertEqual(_model, "third-party-model")
            self.assertEqual(kwargs, {
                "api_format": "anthropic", "auth_mode": "api_key"
            })
            if "CHỈ xuất bản dịch" in prompt:
                return "Dịch xong"
            if "CHARACTER/WORLD REFERENCE" in prompt:
                return json.dumps({
                    "character_bible": "Nhân vật được nhận diện theo bản dịch.",
                    "characters": [{
                        "name": "Ala", "description": "Young woman with a red coat",
                        "face": "Oval face", "hair": "Dark hair",
                        "outfit": "Fixed red coat", "palette": "Red and brown",
                        "source_notes": "Colors proposed for visual consistency",
                        "reference_prompt": "Full-body character sheet",
                    }],
                })
            if "Soạn YouTube tiêu đề" in prompt:
                return json.dumps({
                    "title": "Tiêu đề", "description": "Mô tả",
                    "tags": ["seo"]
                })
            self.fail("Unexpected request")
        api.side_effect = respond
        result = run_full_job(config, JobProgress())
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(api.call_count, 3)  # Translation, profiles and SEO
        self.assertEqual(result["fields"]["translated"], "Dịch xong")

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

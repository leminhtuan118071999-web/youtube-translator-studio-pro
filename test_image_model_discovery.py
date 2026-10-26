"""Image model discovery from official provider catalogs; no paid edits."""
import unittest
from unittest.mock import Mock, patch

from image_model_discovery import (
    GEMINI_EDIT_MODELS, OPENAI_EDIT_MODELS,
    discover_image_models, key_fingerprint, rank_image_models,
    supported_image_model,
)


def fake_response(payload, status=200):
    result = Mock()
    result.ok = status == 200
    result.status_code = status
    result.json.return_value = payload
    return result


class DiscoveryTests(unittest.TestCase):
    def test_known_edit_models_and_text_models_are_distinguished(self):
        self.assertTrue(supported_image_model("Gemini", "gemini-3.1-flash-image"))
        self.assertTrue(supported_image_model("Gemini", "gemini-2.5-flash-image"))
        self.assertFalse(supported_image_model("Gemini", "gemini-3.5-flash-lite"))
        self.assertFalse(supported_image_model("Gemini", "imagen-4.0-generate-001"))
        self.assertTrue(supported_image_model("OpenAI", "gpt-image-2.5-sunburst"))
        self.assertTrue(supported_image_model(
            "OpenAI", "gpt-image-2.5-sunburst-2026-09-08"
        ))
        self.assertFalse(supported_image_model("OpenAI", "gpt-4.1-mini"))
        self.assertFalse(supported_image_model("OpenAI", "gpt-image-1"))
        self.assertFalse(supported_image_model("OpenAI", "../gpt-image-2"))

    def test_rank_prefers_editing_quality_but_never_invents_access(self):
        result = rank_image_models("Gemini", [
            "models/gemini-2.5-flash-image",
            "models/gemini-3.1-flash-image",
            "models/gemini-3.5-flash-lite",
        ])
        self.assertEqual(result, [
            "gemini-3.1-flash-image",
            "gemini-2.5-flash-image",
        ])
        self.assertEqual(rank_image_models("OpenAI", [
            "gpt-image-2.5-flare", "gpt-image-2.5-sunburst",
            "gpt-image-2.5-sunburst-2026-09-08",
            "gpt-4.1-mini",
        ]), [
            "gpt-image-2.5-sunburst",
            "gpt-image-2.5-flare",
            "gpt-image-2.5-sunburst-2026-09-08",
        ])
        self.assertEqual(rank_image_models("Gemini", ["gemini-3.5-flash-lite"]), [])

    @patch("image_model_discovery.requests.get")
    def test_gemini_model_scan_filters_text_compatibility(self, get):
        get.return_value = fake_response({"models": [
            {
                "name": "models/gemini-3.1-flash-image",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-3.5-flash-lite",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-2.5-flash-image",
                "supportedGenerationMethods": ["embedContent"],
            },
        ]})
        models = discover_image_models("Gemini", "super-secret-token")
        self.assertEqual(models, ["gemini-3.1-flash-image"])
        url = get.call_args.args[0]
        kwargs = get.call_args.kwargs
        self.assertEqual(
            url, "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
        )
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "super-secret-token")
        self.assertFalse(kwargs["allow_redirects"])

    @patch("image_model_discovery.requests.get")
    def test_openai_model_scan_filters_text_models(self, get):
        get.return_value = fake_response({"data": [
            {"id": "gpt-4.1-mini"},
            {"id": "gpt-image-2.5-flare"},
            {"id": "gpt-image-2.5-sunburst"},
            {"id": "gpt-image-1"},  # discontinued
        ]})
        self.assertEqual(discover_image_models("OpenAI", "super-secret-token"), [
            "gpt-image-2.5-sunburst", "gpt-image-2.5-flare",
        ])
        self.assertEqual(get.call_args.args[0], "https://api.openai.com/v1/models")
        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"],
            "Bearer super-secret-token",
        )

    @patch("image_model_discovery.requests.get")
    def test_no_images_returns_empty_not_fake_model(self, get):
        get.return_value = fake_response({"data": [{"id": "gpt-4.1-mini"}]})
        self.assertEqual(discover_image_models("OpenAI", "secret"), [])

    @patch("image_model_discovery.requests.get")
    def test_http_errors_do_not_show_sensitive_token(self, get):
        get.return_value = fake_response({"error": "token: secret"}, status=403)
        with self.assertRaises(RuntimeError) as exc:
            discover_image_models("OpenAI", "secret")
        self.assertIn("403", str(exc.exception))
        self.assertNotIn("secret", str(exc.exception))
        self.assertEqual(get.call_count, 1)

    def test_only_digest_stored_for_key(self):
        first = key_fingerprint("Gemini", "very-secret")
        again = key_fingerprint("Gemini", "very-secret")
        other = key_fingerprint("Gemini", "another-secret")
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        self.assertNotIn("very-secret", first)
        self.assertNotEqual(first, key_fingerprint("OpenAI", "very-secret"))

    def test_rejects_invalid_provider_and_blank_token(self):
        with self.assertRaises(ValueError):
            discover_image_models("Groq", "secret")
        with self.assertRaises(ValueError):
            discover_image_models("Gemini", "")
        with self.assertRaises(ValueError):
            rank_image_models("Groq", [])
        with self.assertRaises(ValueError):
            key_fingerprint("Groq", "secret")


if __name__ == "__main__":
    unittest.main()

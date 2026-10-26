"""Unit tests for Thumbnail AI: validation, real request schemas, no secrets."""
import base64
import io
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from thumbnail_ai import (
    GEMINI_IMAGE_MODELS, OPENAI_IMAGE_MODELS, normalize_thumbnail,
    recognize_and_translate, build_edit_prompt, edit_thumbnail,
)


def sample_image(color="blue"):
    im = Image.new("RGB", (640, 360), color)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def response(payload, status=200):
    out = Mock()
    out.ok = status == 200
    out.status_code = status
    out.json.return_value = payload
    return out


class SharedImageProviderTests(unittest.TestCase):
    def test_reuses_only_official_image_capable_main_providers(self):
        from thumbnail_ui import image_provider_for_main_api
        self.assertEqual(image_provider_for_main_api("Google Gemini"), "Gemini")
        self.assertEqual(image_provider_for_main_api("OpenAI"), "OpenAI")
        for provider in (
            "Groq", "Claude (Anthropic)", "Claude Gateway (AUTH_TOKEN)",
            "API bên thứ ba (tùy chỉnh)", "OpenRouter", "DeepSeek", None,
        ):
            with self.subTest(provider=provider):
                self.assertIsNone(image_provider_for_main_api(provider))


class ThumbnailAITests(unittest.TestCase):
    def setUp(self):
        self.picture = sample_image()
        self.b64 = base64.b64encode(self.picture).decode("ascii")

    def test_source_validation_and_16_9_output(self):
        self.assertEqual(Image.open(io.BytesIO(normalize_thumbnail(self.picture))).size,
                         (640, 360))
        for image in (b"abc", b"", b"x" * 9_000_001):
            with self.subTest(image=image[:10]):
                with self.assertRaises(ValueError):
                    normalize_thumbnail(image)

    def test_prompt_keeps_identity_inpaints_old_text_exact_translation(self):
        prompt = build_edit_prompt(
            "translate", "Tiếng Ba Lan",
            original_text="HELP", translated_text="POMOC",
            preserve_layout=True, clean_text=True,
        )
        self.assertIn("EXACTLY", prompt)
        self.assertIn("POMOC", prompt)
        self.assertIn("image inpainting", prompt)
        self.assertIn("without blurry patches", prompt)
        self.assertIn("faces", prompt)
        self.assertIn("Typography", prompt.title())
        self.assertIn("16:9", prompt)
        recreate = build_edit_prompt("recreate", "Tiếng Anh")
        self.assertIn("RECREATE/RESTORE", recreate)
        self.assertIn("Preserve any original visible text exactly", recreate)
        with self.assertRaises(ValueError):
            build_edit_prompt("unknown", "Tiếng Anh")

    @patch("thumbnail_ai.requests.post")
    def test_gemini_ocr_and_translation_uses_vision_input(self, post):
        post.return_value = response({"candidates": [{
            "content": {"parts": [{"text":
                '{"original_text":"HELP","translated_text":"POMOC"}'}]}
        }]})
        o, t = recognize_and_translate(
            self.picture, "Tiếng Ba Lan", "Gemini", "SECRETKEY"
        )
        self.assertEqual((o, t), ("HELP", "POMOC"))
        args, kwargs = post.call_args
        self.assertIn("gemini-3.5-flash-lite:generateContent", args[0])
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "SECRETKEY")
        self.assertEqual(
            kwargs["json"]["contents"][0]["parts"][0]["inlineData"]["data"],
            self.b64,
        )
        self.assertFalse(kwargs["allow_redirects"])

    @patch("thumbnail_ai.requests.post")
    def test_openai_ocr_reads_image_and_requests_json(self, post):
        post.return_value = response({"choices": [{
            "message": {"content": '{"original_text":"STOP","translated_text":"DỪNG"}'}
        }]})
        out = recognize_and_translate(
            self.picture, "Tiếng Việt", "OpenAI", "SECRETKEY"
        )
        self.assertEqual(out, ("STOP", "DỪNG"))
        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["model"], "gpt-4.1-mini")
        self.assertEqual(kwargs["json"]["response_format"]["type"], "json_object")
        self.assertIn("base64,", kwargs["json"]["messages"][0]["content"][1]["image_url"]["url"])

    @patch("thumbnail_ai.requests.post")
    def test_gemini_image_edit_returns_valid_png(self, post):
        post.return_value = response({"candidates": [{
            "content": {"parts": [{
                "inlineData": {"mimeType": "image/png", "data": self.b64}
            }]}
        }]})
        result = edit_thumbnail(
            self.picture, "Recreate this source", "Gemini", "SECRETKEY",
            GEMINI_IMAGE_MODELS[0],
        )
        self.assertEqual(Image.open(io.BytesIO(result)).size, (1280, 720))
        args, kwargs = post.call_args
        self.assertIn("gemini-2.5-flash-image:generateContent", args[0])
        self.assertEqual(
            kwargs["json"]["generationConfig"]["responseModalities"], ["IMAGE"]
        )
        self.assertEqual(
            kwargs["json"]["generationConfig"]["responseFormat"]["image"]["aspectRatio"],
            "16:9",
        )

    @patch("thumbnail_ai.requests.post")
    def test_openai_image_edit_uses_multipart_bytes(self, post):
        post.return_value = response({"data": [{"b64_json": self.b64}]})
        result = edit_thumbnail(
            self.picture, "Keep original", "OpenAI", "SECRETKEY",
            OPENAI_IMAGE_MODELS[0],
        )
        self.assertEqual(Image.open(io.BytesIO(result)).size, (1280, 720))
        url = post.call_args.args[0]
        kwargs = post.call_args.kwargs
        self.assertEqual(url, "https://api.openai.com/v1/images/edits")
        self.assertEqual(kwargs["data"]["size"], "1536x864")
        self.assertEqual(kwargs["data"]["model"], OPENAI_IMAGE_MODELS[0])
        self.assertEqual(kwargs["files"]["image"][1], self.picture)

    @patch("thumbnail_ai.requests.post")
    def test_provider_403_redacts_api_key(self, post):
        post.return_value = response(
            {"error": {"message": "SECRETKEY is not allowed"}}, 403
        )
        with self.assertRaises(RuntimeError) as caught:
            edit_thumbnail(
                self.picture, "rebuild", "Gemini", "SECRETKEY",
                GEMINI_IMAGE_MODELS[0],
            )
        self.assertIn("HTTP 403", str(caught.exception))
        self.assertNotIn("SECRETKEY", str(caught.exception))

    @patch("thumbnail_ai.requests.post")
    def test_gemini_missing_image_does_not_claim_success(self, post):
        post.return_value = response({"candidates": [{
            "content": {"parts": [{"text": "Cannot create this image."}]}
        }]})
        with self.assertRaises(RuntimeError) as err:
            edit_thumbnail(
                self.picture, "rebuild", "Gemini", "SECRETKEY",
                GEMINI_IMAGE_MODELS[0],
            )
        self.assertIn("không trả về ảnh", str(err.exception))

    def test_rejects_unsupported_models_and_invalid_language(self):
        with self.assertRaises(ValueError):
            edit_thumbnail(self.picture, "prompt", "Gemini", "SECRETKEY", "gemini-text")
        with self.assertRaises(ValueError):
            edit_thumbnail(self.picture, "prompt", "OpenAI", "SECRETKEY", "gpt-text")
        with self.assertRaises(ValueError):
            recognize_and_translate(self.picture, "../internal", "Gemini", "SECRETKEY")


if __name__ == "__main__":
    unittest.main()

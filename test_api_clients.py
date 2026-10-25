import socket
import unittest
from unittest.mock import Mock, patch

from api_clients import (
    PROVIDERS,
    api_endpoint,
    generate_text,
    list_models,
    validate_base_url,
)


PUBLIC_ADDR = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]


class ApiClientTests(unittest.TestCase):
    def test_known_providers_present(self):
        for name in ("Groq", "Google Gemini", "OpenAI", "OpenRouter",
                     "DeepSeek", "Together AI", "Anthropic Claude",
                     "API tương thích OpenAI (tùy chỉnh)"):
            self.assertIn(name, PROVIDERS)

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    def test_url_base_appends_chat_endpoint(self, _dns):
        self.assertEqual(
            api_endpoint("https://api.groq.com/openai/v1", "chat", "chat"),
            "https://api.groq.com/openai/v1/chat/completions",
        )
        self.assertEqual(
            api_endpoint("https://api.anthropic.com/v1", "anthropic", "chat"),
            "https://api.anthropic.com/v1/messages",
        )
        self.assertEqual(
            api_endpoint("https://generativelanguage.googleapis.com/v1beta/openai",
                         "chat", "models"),
            "https://generativelanguage.googleapis.com/v1beta/openai/models",
        )

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    def test_public_url_can_be_custom(self, _dns):
        self.assertEqual(
            validate_base_url(" https://external-api.example.com/v1/ "),
            "https://external-api.example.com/v1",
        )

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    def test_reject_private_urls_and_paths(self, _dns):
        for url in (
            "http://api.groq.com/openai/v1",
            "https://localhost/v1",
            "https://10.0.0.1/v1",
            "https://127.0.0.1/v1",
            "https://169.254.169.254/v1",
            "https://metadata.google.internal/v1",
            "https://abc.local/v1",
            "https://user:password@api.groq.com/v1",
            "https://api.groq.com/v1?secret=x",
            "https://api.groq.com:8080/v1",
            "https://api.groq.com/v1/chat/completions",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    api_endpoint(url, "chat", "chat")

    @patch("api_clients.socket.getaddrinfo",
           return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.4", 443))])
    def test_block_private_dns(self, _dns):
        with self.assertRaises(ValueError):
            validate_base_url("https://internal-looking-public.example.org/v1")

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_chat_completions(self, req, _dns):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [{"message": {"content": "Xin chào thế giới"}}]
        }
        req.return_value = response
        result = generate_text("Groq", PROVIDERS["Groq"]["base_url"],
                               "openai/gpt-oss-120b", "secret", "Translate this")
        self.assertEqual(result, "Xin chào thế giới")
        args, kwargs = req.call_args
        self.assertEqual(args[0], "POST")
        self.assertTrue(args[1].endswith("/chat/completions"))
        self.assertEqual(args[2]["Authorization"], "Bearer secret")
        self.assertEqual(kwargs["json"]["model"], "openai/gpt-oss-120b")

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_anthropic_native(self, req, _dns):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "content": [{"type": "text", "text": "Witaj świecie"}]
        }
        req.return_value = response
        result = generate_text("Anthropic Claude",
                               PROVIDERS["Anthropic Claude"]["base_url"],
                               "claude-sonnet-4-5", "secret", "Translate")
        self.assertEqual(result, "Witaj świecie")
        args, kwargs = req.call_args
        self.assertTrue(args[1].endswith("/messages"))
        self.assertEqual(args[2]["x-api-key"], "secret")
        self.assertEqual(kwargs["json"]["messages"][0]["content"], "Translate")

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_scan_models(self, req, _dns):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "data": [{"id": "model-z"}, {"id": "model-a"}, {"id": "model-z"}]
        }
        req.return_value = response
        self.assertEqual(
            list_models("Groq", PROVIDERS["Groq"]["base_url"], "secret"),
            ["model-a", "model-z"],
        )

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_http_error_redacts_key(self, req, _dns):
        resp = Mock()
        resp.ok = False
        resp.status_code = 401
        resp.json.return_value = {
            "error": {"message": "API key SECRET-DO-NOT-PRINT is invalid"}
        }
        req.return_value = resp
        with self.assertRaises(RuntimeError) as result:
            generate_text("Groq", PROVIDERS["Groq"]["base_url"],
                          "openai/gpt-oss-120b", "SECRET-DO-NOT-PRINT", "hi")
        self.assertNotIn("SECRET-DO-NOT-PRINT", str(result.exception))


if __name__ == "__main__":
    unittest.main()

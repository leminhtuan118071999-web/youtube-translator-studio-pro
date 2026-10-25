import socket
import unittest
from unittest.mock import Mock, patch

from api_clients import (
    PROVIDERS,
    RateLimitError,
    api_endpoint,
    generate_text,
    list_models,
    validate_base_url,
    migrate_claude_settings,
)


PUBLIC_ADDR = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]


class ApiClientTests(unittest.TestCase):
    def setUp(self):
        # Exercise pacing independently in test_groq_pacing.py. These API
        # parsing tests must not wait for a rolling TPM window.
        gate = patch("api_clients.groq_request_gate")
        self.mock_gate = gate.start()
        self.addCleanup(gate.stop)

    def test_known_providers_present(self):
        for name in ("Groq", "Google Gemini", "OpenAI", "OpenRouter",
                     "DeepSeek", "Together AI", "Claude (Anthropic)",
                     "API tương thích OpenAI (tùy chỉnh)"):
            self.assertIn(name, PROVIDERS)

    def test_claude_is_a_native_provider_with_current_default(self):
        claude = PROVIDERS["Claude (Anthropic)"]
        self.assertEqual(claude["kind"], "anthropic")
        self.assertEqual(claude["base_url"], "https://api.anthropic.com/v1")
        self.assertEqual(claude["model"], "claude-sonnet-4-6")
        self.assertEqual(claude["secret"], "ANTHROPIC_API_KEY")

    def test_previous_claude_keys_and_model_migrate(self):
        state = {
            "api_provider": "Anthropic Claude",
            "api_key_Anthropic Claude": "sk-ant-sensitive-kept",
            "api_base_Anthropic Claude": "https://api.anthropic.com/v1",
            "api_model_id_Anthropic Claude": "claude-sonnet-4-5",
            "api_key_Groq": "other-provider-unchanged",
        }
        migrate_claude_settings(state)
        self.assertEqual(state["api_provider"], "Claude (Anthropic)")
        self.assertEqual(state["api_key_Claude (Anthropic)"], "sk-ant-sensitive-kept")
        self.assertEqual(state["api_model_id_Claude (Anthropic)"], "claude-sonnet-4-6")
        self.assertNotIn("api_key_Anthropic Claude", state)
        self.assertEqual(state["api_key_Groq"], "other-provider-unchanged")
        migrate_claude_settings(state)
        self.assertEqual(state["api_key_Claude (Anthropic)"], "sk-ant-sensitive-kept")

    def test_migrate_respects_existing_new_claude_values(self):
        state = {
            "api_key_Anthropic Claude": "legacy",
            "api_key_Claude (Anthropic)": "keep-current",
            "api_model_id_Anthropic Claude": "claude-opus-4-5",
        }
        migrate_claude_settings(state)
        self.assertEqual(state["api_key_Claude (Anthropic)"], "keep-current")
        self.assertEqual(state["api_model_id_Claude (Anthropic)"], "claude-opus-4-5")

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
    def test_groq_oss_requests_low_reasoning_with_token_headroom(self, req, _dns):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [{"finish_reason": "stop",
                         "message": {"content": "Tekst przetłumaczony",
                                     "reasoning": "Hidden thoughts"}}]
        }
        req.return_value = response
        result = generate_text(
            "Groq", PROVIDERS["Groq"]["base_url"],
            "openai/gpt-oss-120b", "secret", "Translate"
        )
        self.assertEqual(result, "Tekst przetłumaczony")
        body = req.call_args.kwargs["json"]
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(body["max_completion_tokens"], 2200)
        self.assertFalse(body["include_reasoning"])

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_groq_reports_token_limit_instead_of_generic_error(self, req, _dns):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [{"finish_reason": "length", "message": {
                "content": None, "reasoning": "internal work only"
            }}],
            "usage": {"completion_tokens": 1024}
        }
        req.return_value = response
        with self.assertRaises(RuntimeError) as failure:
            generate_text("Groq", PROVIDERS["Groq"]["base_url"],
                          "openai/gpt-oss-120b", "secret", "Translate")
        text = str(failure.exception)
        self.assertIn("finish_reason=length", text)
        self.assertIn("completion_tokens=1024", text)
        self.assertNotIn("internal work only", text)

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_reasoning_is_never_shown_as_translated_text(self, req, _dns):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [{"finish_reason": "stop", "message": {
                "content": None, "reasoning": "private assistant scratchpad"
            }}]
        }
        req.return_value = response
        with self.assertRaises(RuntimeError) as failure:
            generate_text("Groq", PROVIDERS["Groq"]["base_url"],
                          "openai/gpt-oss-120b", "secret", "Translate")
        self.assertIn("không có nội dung", str(failure.exception))
        self.assertNotIn("private assistant scratchpad", str(failure.exception))

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_openai_compatible_list_response(self, req, _dns):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [{"finish_reason": "stop", "message": {
                "content": [{"type": "text", "text": "English"}, {
                    "type": "text", "text": "Polish"
                }]}
            }]
        }
        req.return_value = response
        result = generate_text("OpenRouter", PROVIDERS["OpenRouter"]["base_url"],
                               "openai/gpt-oss-120b", "secret", "Translate")
        self.assertEqual(result, "English\nPolish")
        self.assertNotIn("reasoning_effort", req.call_args.kwargs["json"])

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_compatible_responses_style(self, req, _dns):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": "Output from proxy"}]}]
        }
        req.return_value = response
        result = generate_text("OpenAI", PROVIDERS["OpenAI"]["base_url"],
                               "gpt-4.1-mini", "secret", "Translate")
        self.assertEqual(result, "Output from proxy")

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_gemini_native_style_fallback(self, req, _dns):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "candidates": [{"finishReason": "STOP", "content": {
                "parts": [{"text": "Przetłumaczony tekst."}]
            }}]
        }
        req.return_value = response
        result = generate_text("Google Gemini", PROVIDERS["Google Gemini"]["base_url"],
                               "gemini-3.8-flash", "secret", "Translate")
        self.assertEqual(result, "Przetłumaczony tekst.")

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_anthropic_native(self, req, _dns):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "content": [{"type": "text", "text": "Witaj świecie"}]
        }
        req.return_value = response
        result = generate_text("Claude (Anthropic)",
                               PROVIDERS["Claude (Anthropic)"]["base_url"],
                               "claude-sonnet-4-6", "secret", "Translate")
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
    def test_groq_429_uses_retry_after_header(self, req, _dns):
        resp = Mock()
        resp.ok = False
        resp.status_code = 429
        resp.headers = {"retry-after": "11.5"}
        resp.json.return_value = {
            "error": {"message": "Rate limit reached for TPM. Please try again in 11.52s."}
        }
        req.return_value = resp
        with self.assertRaises(RateLimitError) as error:
            generate_text("Groq", PROVIDERS["Groq"]["base_url"],
                          "openai/gpt-oss-120b", "secret-key", "Translate")
        self.assertAlmostEqual(error.exception.retry_after, 11.5)
        self.assertTrue(error.exception.can_retry)

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_429_reads_delay_from_message_if_header_missing(self, req, _dns):
        resp = Mock()
        resp.ok = False
        resp.status_code = 429
        resp.headers = {}
        resp.json.return_value = {
            "error": {"message": "Rate limit reached. Please try again in 11.52s."}
        }
        req.return_value = resp
        with self.assertRaises(RateLimitError) as error:
            generate_text("Groq", PROVIDERS["Groq"]["base_url"],
                          "openai/gpt-oss-120b", "secret", "Translate")
        self.assertAlmostEqual(error.exception.retry_after, 11.52)

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_429_daily_quota_does_not_retry(self, req, _dns):
        resp = Mock()
        resp.ok = False
        resp.status_code = 429
        resp.headers = {}
        resp.json.return_value = {
            "error": {"message": "Tokens per day (TPD) quota exceeded"}
        }
        req.return_value = resp
        with self.assertRaises(RateLimitError) as error:
            generate_text("Groq", PROVIDERS["Groq"]["base_url"],
                          "openai/gpt-oss-120b", "secret", "Translate")
        self.assertFalse(error.exception.can_retry)

    @patch("api_clients.socket.getaddrinfo", return_value=PUBLIC_ADDR)
    @patch("api_clients._request")
    def test_groq_prompts_reserve_more_output_than_translation(self, req, _dns):
        resp = Mock()
        resp.ok = True
        resp.json.return_value = {
            "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]
        }
        req.return_value = resp
        generate_text("Groq", PROVIDERS["Groq"]["base_url"],
                      "openai/gpt-oss-120b", "secret", "Hãy viết ĐÚNG 20 prompt")
        self.assertEqual(req.call_args.kwargs["json"]["max_completion_tokens"], 3600)

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

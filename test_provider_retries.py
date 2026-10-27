import unittest
from unittest.mock import Mock, patch

from api_clients import RateLimitError, TransientProviderError
from provider_retries import retry_transient_provider


class DirectProviderRetryTests(unittest.TestCase):
    def test_gateway_failure_retries_identical_operation_and_recovers(self):
        for status in (502, 503, 504):
            with self.subTest(status=status):
                operation = Mock(side_effect=[TransientProviderError("upstream", status), "answer"])
                wait, report = Mock(), Mock()
                self.assertEqual(retry_transient_provider(operation, wait=wait, report=report), "answer")
                self.assertEqual(operation.call_count, 2)
                wait.assert_called_once_with(3.0)
                self.assertIn(f"HTTP {status}", report.call_args.args[0])

    def test_persistent_failure_stops_after_three_retries(self):
        operation = Mock(side_effect=TransientProviderError("upstream", 502))
        wait = Mock()
        with self.assertRaises(TransientProviderError) as caught:
            retry_transient_provider(operation, wait=wait)
        self.assertEqual(operation.call_count, 4)
        self.assertEqual([c.args[0] for c in wait.call_args_list], [3, 6, 12])
        self.assertIn("sau 3 lần thử lại", str(caught.exception))
        self.assertEqual(caught.exception.status_code, 502)

    def test_retry_after_is_respected_and_bounded(self):
        for stated, expected in ((30, 30), (0, 1), (999, 180), (float("nan"), 3), ("bad", 3)):
            with self.subTest(stated=stated):
                operation = Mock(side_effect=[TransientProviderError("upstream", 503, stated), "answer"])
                wait = Mock()
                retry_transient_provider(operation, wait=wait)
                wait.assert_called_once_with(expected)

    def test_invalid_credentials_quota_and_unknown_failures_are_not_retried(self):
        for failure in (RuntimeError("HTTP 401"), RuntimeError("HTTP 404"),
                        RateLimitError("quota", can_retry=False),
                        ValueError("bad configuration"), TransientProviderError("unknown", 500)):
            with self.subTest(failure=failure):
                operation, wait = Mock(side_effect=failure), Mock()
                with self.assertRaises(type(failure)):
                    retry_transient_provider(operation, wait=wait)
                self.assertEqual(operation.call_count, 1)
                wait.assert_not_called()

    def test_manual_translation_recovers_and_preserves_old_result_if_gateway_stays_down(self):
        from streamlit.testing.v1 import AppTest
        from background_jobs import JobProgress
        from faithful_summary import optimize_source_script
        for persistent in (False, True):
            with self.subTest(persistent=persistent):
                app = AppTest.from_file("streamlit_app.py", default_timeout=20)
                for name in ("_browser_sessions_restored", "_browser_api_restored", "_session_name_test_fallback"):
                    app.session_state[name] = True
                app.session_state["api_provider"] = "OpenAI"
                app.session_state["api_key_OpenAI"] = "test-secret"
                app.run()
                self.assertFalse(app.exception)
                sid = app.session_state["selected_session"]
                progress = JobProgress()
                original = "Nora visits Maisie."
                optimized = optimize_source_script(original, lambda _: '{"edits":[],"unresolved":[]}', progress)
                record = app.session_state["workspaces"][sid]
                record.update(source=original, optimized_script=optimized, translated="Old translation",
                              optimization_review_json=progress.partial_result()["optimization_review_json"])
                app.run()
                prompts = []
                def api(_provider, _base, _model, _key, prompt, **_options):
                    prompts.append(prompt)
                    if persistent or len(prompts) == 1:
                        raise TransientProviderError("Upstream service temporarily unavailable", 502)
                    if prompt.startswith("FAITHFULNESS_REVIEW"):
                        return '{"ok":true,"issues":[],"source_conflicts":[]}'
                    return "Nora odwiedza Maisie."
                with patch("api_clients.generate_text", side_effect=api), patch("provider_retries._sleep") as wait:
                    next(x for x in app.button if x.key == f"translate_{sid}").click().run()
                self.assertFalse(app.exception, [e.message for e in app.exception])
                record = app.session_state["workspaces"][sid]
                self.assertEqual(record["source"], original)
                if persistent:
                    self.assertEqual(record["translated"], "Old translation")
                    self.assertEqual(len(prompts), 4)
                    self.assertEqual(wait.call_count, 3)
                    self.assertTrue(any("HTTP 502" in x.value for x in app.error))
                else:
                    self.assertEqual(record["translated"], "Nora odwiedza Maisie.")
                    self.assertEqual(len(prompts), 3)
                    self.assertEqual(prompts[0], prompts[1])
                    wait.assert_called_once_with(3.0)


if __name__ == "__main__":
    unittest.main()

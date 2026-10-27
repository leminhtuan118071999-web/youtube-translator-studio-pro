import json
import socket
import unittest
from unittest.mock import Mock, patch

from api_clients import generate_text
from background_jobs import JobProgress
from faithful_summary import optimize_source_script, source_windows, source_hash
from generation_budgets import task_output_budget
from groq_pacing import estimated_tokens
from section_retries import prepare_reviewed_script


def summary_response(prompt):
    part = json.loads(prompt.split("SOURCE DATA:\n", 1)[1])
    return json.dumps({"summary": "Nora visits Maisie. Luca waits outside.",
                       "entities": [], "edits": [], "unresolved": [],
                       "anchors": [{"fact": "A visit", "quote": part["core"].strip()[:70]}]})


class FastWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.source = ("Nora visited Maisie. Luca waited outside.\n" * 1000).strip()

    def test_long_source_uses_two_calls_per_part_and_no_separate_repair_pass(self):
        calls = []
        def call(prompt):
            calls.append(prompt)
            if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
                return summary_response(prompt)
            self.assertTrue(prompt.startswith("FAITHFULNESS_REVIEW"))
            return '{"ok":true,"issues":[],"source_conflicts":[]}'
        result = optimize_source_script(self.source, call, JobProgress())
        new_parts = len(source_windows(self.source, limit=6000))
        old_parts = len(source_windows(self.source))
        self.assertEqual(len(calls), 2 * new_parts)
        self.assertLess(len(calls), 3 * old_parts * 0.5)
        self.assertLess(len(result), 10000)

    def test_resume_skips_completed_reviewed_parts(self):
        progress = JobProgress()
        seen = []
        def interrupted(prompt):
            seen.append(prompt)
            if len(seen) > 2:
                raise RuntimeError("temporary gateway outage")
            return summary_response(prompt) if prompt.startswith("SOURCE_GROUNDED_SUMMARY") else '{"ok":true,"issues":[],"source_conflicts":[]}'
        with self.assertRaises(RuntimeError):
            optimize_source_script(self.source, interrupted, progress)
        checkpoint = progress.partial_result()["optimization_work_json"]
        self.assertEqual(len(json.loads(checkpoint)["summaries"]), 1)
        resumed = JobProgress()
        resumed.publish("optimization_work_json", checkpoint)
        calls = []
        def call(prompt):
            calls.append(prompt)
            return summary_response(prompt) if prompt.startswith("SOURCE_GROUNDED_SUMMARY") else '{"ok":true,"issues":[],"source_conflicts":[]}'
        optimize_source_script(self.source, call, resumed)
        self.assertEqual(len(calls), 2 * (len(source_windows(self.source, limit=6000)) - 1))
        self.assertEqual(resumed.partial_result()["optimization_work_json"], "")

    def test_fused_source_repair_is_still_reviewed_against_original(self):
        source = "Nora were tired.\n" + self.source
        def call(prompt):
            if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
                data = json.loads(summary_response(prompt))
                if "Nora were tired." in prompt:
                    data["summary"] = "Nora was tired. She visited Maisie while Luca waited."
                    data["edits"] = [{"before": "Nora were tired.", "after": "Nora was tired.",
                        "kind": "language", "confidence": "high", "reason": "Sửa ngữ pháp", "evidence": []}]
                return json.dumps(data)
            data = json.loads(prompt.split("instructions:\n", 1)[1])
            if data["context"]["proposed_source_repairs"]:
                self.assertIn("Nora were tired.", data["original"])
                self.assertIn("Nora was tired.", data["candidate"])
            return '{"ok":true,"issues":[],"source_conflicts":[]}'
        progress = JobProgress()
        optimize_source_script(source, call, progress)
        report = json.loads(progress.partial_result()["optimization_review_json"])
        self.assertEqual(len(report["source_repairs"]), 1)
        self.assertEqual(report["source_sha256"], source_hash(source))
        self.assertNotEqual(report["prepared_source_sha256"], report["source_sha256"])

    def test_version_three_approved_script_is_reused_without_reprocessing(self):
        source = "Nora visits Maisie."
        record = {"source": source, "optimized_script": source,
                  "optimization_review_json": json.dumps({"version": 3,
                      "source_sha256": source_hash(source), "output_sha256": source_hash(source)})}
        self.assertEqual(prepare_reviewed_script(record, lambda _: self.fail("Already approved"), JobProgress()), {})

    @patch("api_clients.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    @patch("api_clients.groq_request_gate")
    @patch("api_clients._request")
    def test_request_budget_matches_pacing_and_provider_payload(self, request, _gate, _dns):
        response = Mock(ok=True)
        response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}],
            "content": [{"type": "text", "text": "OK"}],
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}],
        }
        request.return_value = response
        for marker, expected in (("FAITHFULNESS_REVIEW", 1024), ("SOURCE_GROUNDED_SUMMARY", 3072)):
            prompt = marker + ". " + "source data " * 50
            self.assertEqual(task_output_budget(prompt), expected)
            for provider, base, model, field in (
                ("Groq", "https://api.groq.com/openai/v1", "openai/gpt-oss-20b", "max_completion_tokens"),
                ("Claude (Anthropic)", "https://api.anthropic.com/v1", "test-model", "max_tokens"),
                ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta", "gemini-test", "generationConfig"),
            ):
                with self.subTest(marker=marker, provider=provider):
                    self.assertEqual(generate_text(provider, base, model, "secret", prompt), "OK")
                    body = request.call_args.kwargs["json"]
                    actual = body[field]["maxOutputTokens"] if field == "generationConfig" else body[field]
                    self.assertEqual(actual, expected)
        body = "x" * 1500
        self.assertLess(estimated_tokens("FAITHFULNESS_REVIEW " + body), estimated_tokens("old review " + body))


if __name__ == "__main__":
    unittest.main()

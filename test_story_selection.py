import json
import unittest
from unittest.mock import patch
from background_jobs import JobProgress, run_full_job
from faithful_summary import rewrite_target_script, source_hash
from story_selection import validate_selection


class StorySelectionTests(unittest.TestCase):
    source = "Unrelated opening. Nora is Maisie's mother. Nora paid 268000 USD to save Maisie. Maisie survived. Another unrelated plot."
    target = "Nora, matka Maisie, zapłaciła 268000 USD, by ją uratować. Maisie przeżyła."

    def plan(self):
        return dict(first_part=1, last_part=1, opening_quote="Nora paid 268000 USD to save Maisie.",
                    ending_quote="Maisie survived.", background_quotes=["Nora is Maisie's mother."],
                    reason="Một cuộc giải cứu có kết quả rõ ràng.")

    def provider(self, prompt):
        self.calls.append(prompt)
        if prompt.startswith("STORY_ARC_SELECTION"):
            self.assertIn(self.source, prompt)
            return json.dumps(self.plan())
        if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
            data = json.loads(prompt.split("SOURCE DATA:\n")[1])
            self.assertNotIn("Unrelated", data["core"])
            self.assertIn("Nora is Maisie's mother.", str(data["context"]))
            return json.dumps(dict(summary=self.target, entities=["Nora", "Maisie"],
                anchors=[dict(fact="Nora paid", quote="Nora paid 268000 USD")]))
        if prompt.startswith("FAITHFULNESS_REVIEW"):
            return '{"ok":true,"issues":[],"source_conflicts":[]}'
        if "CHARACTER/WORLD REFERENCE" in prompt:
            return '{"character_bible":"Nora","characters":[]}'
        if "Soạn YouTube tiêu đề" in prompt:
            return '{"title":"Title","description":"Description","tags":["tag"]}'
        self.fail(prompt[:100])

    def setUp(self):
        self.calls = []

    def test_extracts_contiguous_arc_with_original_background_and_whole_story_review(self):
        progress = JobProgress()
        result = rewrite_target_script(self.source, "Polish", self.provider, progress)
        self.assertEqual(result, self.target)
        report = json.loads(progress.partial_result()["optimization_review_json"])
        self.assertEqual(report["method"], "selected_story_target")
        self.assertEqual(report["source_sha256"], source_hash(self.source))
        selected = self.source[report["story_selection"]["start"]:report["story_selection"]["end"]]
        self.assertEqual(selected, "Nora paid 268000 USD to save Maisie. Maisie survived.")
        self.assertEqual(sum(p.startswith("FAITHFULNESS_REVIEW") for p in self.calls), 2)
        self.assertLess(len(result), 9000)

    def test_rejects_invented_boundary_background_and_reversed_range(self):
        for change in [dict(opening_quote="Invented"), dict(background_quotes=["Nora is a queen"]),
                       dict(first_part=2), dict(ending_quote="Unrelated opening.")]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_selection({**self.plan(), **change}, self.source, [{"core": self.source}])

    def test_failed_global_audit_does_not_publish_output_and_discards_bad_chunks(self):
        progress = JobProgress()
        def call(prompt):
            if 'whole_story_check' in prompt:
                return '{"ok":false,"issues":["Wrong relationship"],"source_conflicts":[]}'
            return self.provider(prompt)
        with self.assertRaisesRegex(ValueError, "Wrong relationship"):
            rewrite_target_script(self.source, "Polish", call, progress)
        self.assertNotIn("optimization_review_json", progress.partial_result())
        self.assertNotIn("chunk_work", json.loads(progress.partial_result()["optimization_work_json"]))

    def test_resume_does_not_repeat_selection_or_accepted_chunks(self):
        progress = JobProgress()
        def call(prompt):
            if 'whole_story_check' in prompt:
                raise RuntimeError("network interrupted")
            return self.provider(prompt)
        with self.assertRaises(RuntimeError):
            rewrite_target_script(self.source, "Polish", call, progress)
        self.calls.clear()
        self.assertEqual(rewrite_target_script(self.source, "Polish", self.provider, progress), self.target)
        self.assertEqual(len(self.calls), 1)
        self.assertIn("whole_story_check", self.calls[0])

    def test_invalid_json_selection_is_retried_once(self):
        count = 0
        def call(prompt):
            nonlocal count
            if prompt.startswith("STORY_ARC_SELECTION"):
                count += 1
                if count == 1:
                    return "malformed JSON"
            return self.provider(prompt)
        self.assertEqual(rewrite_target_script(self.source, "Polish", call, JobProgress()), self.target)
        self.assertEqual(count, 2)

    def test_start_uses_new_selection_and_preserves_original(self):
        cfg = dict(source=self.source, url="", language="Polish", provider="OpenAI",
                   base_url="https://api.openai.com/v1", model="test", api_key="secret")
        with patch("background_jobs.generate_text", side_effect=lambda p,b,m,k,prompt,**kw:self.provider(prompt)):
            result = run_full_job(cfg, JobProgress())
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["fields"]["source"], self.source)
        self.assertEqual(result["fields"]["translated"], self.target)

if __name__ == '__main__':
    unittest.main()

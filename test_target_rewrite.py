import json
import unittest
from unittest.mock import patch

from background_jobs import JobProgress, run_full_job
from faithful_summary import rewrite_target_script, source_windows, MAX_TARGET_SCRIPT_CHARS
from section_retries import rerun_target_rewrite


def draft(prompt, text):
    data = json.loads(prompt.split("SOURCE DATA:\n", 1)[1])
    return json.dumps({"summary": text, "entities": [], "edits": [], "unresolved": [],
        "anchors": [{"fact": "Original plot and important actions", "quote": data["core"].strip()[:100]}]})


def approved():
    return '{"ok":true,"issues":[],"source_conflicts":[]}'


class TargetRewriteTests(unittest.TestCase):
    def test_start_rewrites_original_directly_into_target_and_feeds_downstream(self):
        original = "Nora paid 268000 USD to save Maisie. Luca learned Enzo was Maisie's father."
        target = "Nora zapłaciła 268000 USD, aby uratować Maisie. Luca odkrył, że jej ojcem był Enzo."
        calls = []
        def provider(_p, _base, _m, _key, prompt, **_options):
            calls.append(prompt)
            if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
                self.assertIn(original, prompt)
                self.assertIn("Tiếng Ba Lan", prompt)
                return draft(prompt, target)
            if prompt.startswith("FAITHFULNESS_REVIEW"):
                data = json.loads(prompt.split("instructions:\n", 1)[1])
                self.assertEqual(data["mode"], "target_rewrite")
                self.assertEqual(data["original"], original)
                self.assertEqual(data["candidate"], target)
                return approved()
            if "CHARACTER/WORLD REFERENCE" in prompt:
                self.assertIn(target, prompt)
                return '{"character_bible":"Nora and Luca","characters":[]}'
            if "Soạn YouTube tiêu đề" in prompt:
                self.assertIn(target, prompt)
                return '{"title":"Title","description":"Description","tags":["tag"]}'
            self.fail("Unexpected intermediate pass: " + prompt[:90])
        cfg = {"source": original, "url": "", "language": "Tiếng Ba Lan",
               "provider": "OpenAI", "base_url": "https://api.openai.com/v1",
               "model": "test", "api_key": "secret"}
        with patch("background_jobs.generate_text", side_effect=provider):
            result = run_full_job(cfg, JobProgress())
        self.assertTrue(result["ok"], result["error"])
        fields = result["fields"]
        self.assertEqual(fields["source"], original)
        self.assertEqual(fields["translated"], target)
        self.assertEqual(fields["optimized_script"], target)
        self.assertLess(len(fields["translated"]), 9000)
        self.assertFalse(any("CHỈ xuất bản dịch" in p or p.startswith("STORY_REPAIR_PLAN") for p in calls))
        report = json.loads(fields["optimization_review_json"])
        self.assertEqual(report["method"], "direct_target_rewrite")
        self.assertEqual(report["max_characters"], 8999)
        self.assertEqual(report["target_language"], "Tiếng Ba Lan")

    def test_oversized_target_is_rewritten_from_original_not_clipped(self):
        original = "Nora's sacrifice saved Maisie. The family adopted her."
        seen = []
        def call(prompt):
            if prompt.startswith("FAITHFULNESS_REVIEW"):
                return approved()
            seen.append(json.loads(prompt.split("SOURCE DATA:\n", 1)[1])["core"])
            return draft(prompt, "x" * 9000 if len(seen) == 1 else "Nora uratowała Maisie; rodzina ją adoptowała.")
        text = rewrite_target_script(original, "Polish", call, JobProgress())
        self.assertEqual(seen, [original, original])
        self.assertIn("adoptowała", text)
        self.assertLess(len(text), 9000)
        self.assertEqual(MAX_TARGET_SCRIPT_CHARS, 8999)

    def test_wrong_actor_relationship_number_or_language_requires_correction(self):
        original = "On Nora's birthday, the fake orderly grabbed Nora. Nora paid 268000 USD; Victor froze an allowance."
        good = "W urodziny Nory fałszywy sanitariusz ją chwycił. Nora wpłaciła 268000 USD; Victor zamroził zasiłek."
        for reason in ("Wrong actor", "Wrong birthday owner", "Merged financial facts", "Wrong target language"):
            with self.subTest(reason=reason):
                drafts = []
                def call(prompt):
                    if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
                        drafts.append(prompt)
                        return draft(prompt, good if reason in prompt else "Incorrect target story")
                    data = json.loads(prompt.split("instructions:\n", 1)[1])
                    self.assertEqual(data["original"], original)
                    if data["candidate"] != good:
                        return json.dumps({"ok": False, "issues": [reason], "source_conflicts": []})
                    return approved()
                self.assertEqual(rewrite_target_script(original, "Polish", call, JobProgress()), good)
                self.assertEqual(len(drafts), 2)

    def test_all_source_parts_and_ending_are_covered_with_global_final_budget(self):
        original = "Nora visits Maisie. Luca waits.\n" * 600 + "Enzo is revealed as her father. They adopt Maisie."
        cores = []
        def call(prompt):
            if prompt.startswith("FAITHFULNESS_REVIEW"):
                return approved()
            core = json.loads(prompt.split("SOURCE DATA:\n", 1)[1])["core"]
            cores.append(core)
            return draft(prompt, "Ujawniono ojcostwo Enza i adoptowano Maisie." if core.endswith("They adopt Maisie.")
                         else "Nora odwiedza Maisie, a Luca czeka.")
        result = rewrite_target_script(original, "Polish", call, JobProgress())
        self.assertEqual("".join(cores), original)
        self.assertTrue(result.endswith("adoptowano Maisie."))
        self.assertLess(len(result), 9000)

    def test_checkpoint_is_not_reused_for_different_target_language(self):
        original = "Nora visits Maisie. Luca waits.\n" * 600
        progress = JobProgress()
        count = 0
        def interrupted(prompt):
            nonlocal count
            count += 1
            if count > 2:
                raise RuntimeError("gateway unavailable")
            return approved() if prompt.startswith("FAITHFULNESS_REVIEW") else draft(prompt, "Polish draft")
        with self.assertRaises(RuntimeError):
            rewrite_target_script(original, "Polish", interrupted, progress)
        resumed = JobProgress()
        resumed.publish("optimization_work_json", progress.partial_result()["optimization_work_json"])
        cores = []
        def call(prompt):
            if prompt.startswith("FAITHFULNESS_REVIEW"):
                return approved()
            cores.append(json.loads(prompt.split("SOURCE DATA:\n", 1)[1])["core"])
            return draft(prompt, "New English draft")
        result = rewrite_target_script(original, "English", call, resumed)
        self.assertEqual(len(cores), len(source_windows(original, limit=5000)))
        self.assertNotIn("Polish draft", result)

    def test_manual_retry_uses_original_and_preserves_old_output_if_rejected(self):
        original = "Nora pays to save Maisie."
        session = {"source": original, "optimized_script": "Old summary", "translated": "Old target"}
        previous = dict(session)
        def call(prompt):
            if prompt.startswith("FAITHFULNESS_REVIEW"):
                return '{"ok":false,"issues":["Critical hook missing"],"source_conflicts":[]}'
            self.assertNotIn("Old summary", prompt)
            return draft(prompt, "Bad draft")
        with self.assertRaises(ValueError):
            rerun_target_rewrite(session, "Polish", call, JobProgress())
        self.assertEqual(session, previous)


if __name__ == "__main__":
    unittest.main()

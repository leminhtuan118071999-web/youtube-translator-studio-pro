from test_selection_helpers import whole_source_selection
import json
import re
import unittest
from unittest.mock import patch

from background_jobs import JobProgress, run_full_job
from faithful_summary import (
    optimize_source_script, source_windows, translate_part_faithfully,
    MAX_OPTIMIZED_SCRIPT_CHARS, source_hash, OPTIMIZATION_VERSION,
)


def accepted(conflicts=None):
    return json.dumps({"ok": True, "issues": [], "source_conflicts": conflicts or []})


def draft(prompt, summary):
    source = json.loads(prompt.split("SOURCE DATA:\n", 1)[1])
    quote = source["core"].strip()[:100]
    return json.dumps({"summary": summary, "entities": [],
                       "anchors": [{"fact": "Source event", "quote": quote}]})


class FaithfulSummaryTests(unittest.TestCase):
    def setUp(self):
        # Source repair is covered independently in test_story_repair.py.
        repair = patch("faithful_summary.repair_source_script",
                       side_effect=lambda source, call, progress: (source, [], []))
        repair.start()
        self.addCleanup(repair.stop)

    def test_short_sources_are_preserved_exactly_without_model_rewrite(self):
        for length in (20, 9999):
            text = ("Nora 中文 ć " * 1000)[:length]
            progress = JobProgress()
            result = optimize_source_script(text, lambda _: self.fail("No rewriting needed"), progress)
            self.assertEqual(result, text.strip())
            report = json.loads(progress.partial_result()["optimization_review_json"])
            self.assertEqual(report["method"], "verbatim")
            self.assertEqual(report["output_sha256"], source_hash(result))

    def test_source_windows_cover_middle_ending_and_boundary_context(self):
        source = "Opening. " + "Long passage. " * 900 + "Final reveal and ending."
        windows = source_windows(source)
        self.assertEqual("".join(w["core"] for w in windows), source)
        self.assertTrue(windows[-1]["core"].endswith("ending."))
        for left, right in zip(windows, windows[1:]):
            self.assertTrue(left["core"].endswith(right["before"]))
            self.assertTrue(right["core"].startswith(left["after"]))

    def test_allocates_final_budget_and_reviews_every_part_without_recursive_reduction(self):
        source = "Nora visits Maisie. Luca follows Nora. " * 500 + "The final adoption."
        generated, reviewed, targets = [], [], []
        def call(prompt):
            if prompt.startswith("STORY_ARC_SELECTION"):
                return whole_source_selection(prompt)
            if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
                data = json.loads(prompt.split("SOURCE DATA:\n", 1)[1])
                generated.append(data["core"])
                targets.append(int(re.search(r"tối đa (\d+) ký tự", prompt)[1]))
                return draft(prompt, "Nora visits Maisie and Luca follows her.")
            data = json.loads(prompt.split("instructions:\n", 1)[1])
            reviewed.append(data["original"])
            return accepted(["The original timeline is ambiguous."])
        progress = JobProgress()
        result = optimize_source_script(source, call, progress)
        self.assertEqual("".join(generated), source)
        self.assertEqual(generated, reviewed)
        self.assertLess(sum(targets) + 2 * (len(targets) - 1), 10000)
        self.assertLess(len(result), 10000)
        report = json.loads(progress.partial_result()["optimization_review_json"])
        self.assertEqual(report["reviewed_parts"], len(generated))
        self.assertEqual(len(report["source_conflicts"]), 1)

    def test_rejected_factual_errors_are_repaired_from_original(self):
        # Regression scenarios based on the user's screenshots. These test
        # that detected factual failures control the pipeline, not AI accuracy.
        cases = [
            ("The fake orderly reached toward the syringe tray. Nora raised the alarm.",
             "Luca reached toward the syringe tray.",
             "The fake orderly reached for the tray; Nora raised the alarm.", "Wrong actor"),
            ("Nora transferred 268000 USD to the hospital. Victor froze last month's allowance.",
             "Victor froze 268000 USD.",
             "Nora paid 268000 USD to the hospital; Victor froze the previous allowance.", "Two financial facts merged"),
            ("Jess is Maisie's mother. Jess overdosed. Luca's mother died from lymphoma at home.",
             "Luca's mother overdosed at the hospital.",
             "Jess, Maisie's mother, overdosed. Luca's mother died of lymphoma at home.", "Wrong mother and death location"),
            ("Luca missed Nora's birthday. Maisie discussed Nora's green dress.",
             "Luca missed Maisie's birthday.",
             "Luca missed Nora's birthday; Maisie mentioned Nora's green dress.", "Wrong birthday owner"),
            ("One syringe matching the hospital syringe was found in the vehicle.",
             "Two identical syringes were found in the vehicle.",
             "One matching syringe was found in the vehicle.", "Wrong object count"),
        ]
        for original, bad, good, reason in cases:
            with self.subTest(reason=reason):
                source = (original + "\n") * 180
                def call(prompt):
                    if prompt.startswith("STORY_ARC_SELECTION"):
                        return whole_source_selection(prompt)
                    if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
                        return draft(prompt, good if reason in prompt else bad)
                    data = json.loads(prompt.split("instructions:\n", 1)[1])
                    if data["candidate"] == bad:
                        return json.dumps({"ok": False, "issues": [reason], "source_conflicts": []})
                    self.assertEqual(data["candidate"], good)
                    return accepted()
                result = optimize_source_script(source, call, JobProgress())
                self.assertNotIn(bad, result)
                self.assertIn(good, result)

    def test_fabricated_evidence_is_rejected_before_acceptance(self):
        source = "Nora visits Maisie in the hospital. " * 500
        calls = []
        def call(prompt):
            if prompt.startswith("STORY_ARC_SELECTION"):
                return whole_source_selection(prompt)
            calls.append(prompt)
            return json.dumps({"summary": "A summary.", "entities": ["InventedPerson"],
                "anchors": [{"fact": "Invented event", "quote": "This is not in the original"}]})
        with self.assertRaisesRegex(ValueError, "bằng chứng"):
            optimize_source_script(source, call, JobProgress())
        self.assertEqual(len(calls), 2)

    def test_review_failure_never_publishes_unchecked_summary(self):
        source = "Nora visits Maisie in the hospital. " * 500
        progress = JobProgress()
        def call(prompt):
            if prompt.startswith("STORY_ARC_SELECTION"):
                return whole_source_selection(prompt)
            if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
                return draft(prompt, "Nora visits Maisie.")
            return '{"ok":false,"issues":["Ending omitted"],"source_conflicts":[]}'
        with self.assertRaisesRegex(ValueError, "Ending omitted"):
            optimize_source_script(source, call, progress)
        self.assertNotIn("optimization_review_json", progress.partial_result())

    def test_translation_rechecks_actor_and_uses_neighboring_context(self):
        prompts = []
        def call(prompt):
            if prompt.startswith("STORY_ARC_SELECTION"):
                return whole_source_selection(prompt)
            prompts.append(prompt)
            if prompt.startswith("FAITHFULNESS_REVIEW"):
                data = json.loads(prompt.split("instructions:\n", 1)[1])
                if data["candidate"] == "Luca sięgnął po strzykawkę.":
                    return '{"ok":false,"issues":["Wrong actor: fake orderly, not Luca"],"source_conflicts":[]}'
                return accepted()
            self.assertIn("Nora saw the fake orderly", prompt)
            return ("Fałszywy sanitariusz sięgnął po strzykawkę." if "Wrong actor" in prompt
                    else "Luca sięgnął po strzykawkę.")
        result = translate_part_faithfully("He reached for the syringe.", "Polish", call,
                                         before="Nora saw the fake orderly.")
        self.assertIn("sanitariusz", result)
        self.assertEqual(len(prompts), 4)

    def test_invalid_review_cannot_silently_approve_translation(self):
        def call(prompt):
            if prompt.startswith("STORY_ARC_SELECTION"):
                return whole_source_selection(prompt)
            return "Looks correct" if prompt.startswith("FAITHFULNESS_REVIEW") else "Draft translation"
        with self.assertRaisesRegex(ValueError, "đối soát"):
            translate_part_faithfully("Original", "Polish", call)

    def test_legacy_resume_invalidates_unreviewed_translation(self):
        source = "Original story."
        cfg = {"source": source, "url": "", "language": "English",
               "provider": "OpenAI", "base_url": "https://api.openai.com/v1",
               "model": "test", "api_key": "SECRET", "resume_fields": {
                   "source": source, "optimized_script": "Old wrong summary",
                   "translation_complete": True, "translated": "Old wrong translation",
                   "translation_parts": ["Old wrong translation"],
               }}
        def call(_provider, _base, _model, _key, prompt):
            if prompt.startswith("STORY_ARC_SELECTION"):
                return whole_source_selection(prompt)
            if prompt.startswith("FAITHFULNESS_REVIEW"):
                return accepted()
            if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
                self.assertIn(source, prompt)
                self.assertNotIn("Old wrong summary", prompt)
                return json.dumps({"summary":"New checked translation", "entities":[], "edits":[], "unresolved":[],
                    "anchors":[{"fact":"Original story","quote":source}]})
            if "CHỈ xuất bản dịch" in prompt:
                self.assertIn(source, prompt)
                self.assertNotIn("Old wrong summary", prompt)
                return "New checked translation"
            if "CHARACTER/WORLD REFERENCE" in prompt:
                return '{"character_bible":"Reference","characters":[]}'
            if "Soạn YouTube tiêu đề" in prompt:
                return '{"title":"Title","description":"Description","tags":["tag"]}'
            self.fail(prompt[:80])
        with patch("background_jobs.generate_text", side_effect=call):
            result = run_full_job(cfg, JobProgress())
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["fields"]["translated"], "New checked translation")
        self.assertEqual(MAX_OPTIMIZED_SCRIPT_CHARS, 9999)


if __name__ == "__main__":
    unittest.main()

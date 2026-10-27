import json
import unittest

from background_jobs import JobProgress
from faithful_summary import repair_source_script, optimize_source_script, OPTIMIZATION_VERSION
from section_retries import prepare_reviewed_script, rerun_translation


def plan(edits=None, unresolved=None):
    return json.dumps({"edits": edits or [], "unresolved": unresolved or []})


def edit(before, after, *, kind="language", evidence=None):
    return {"before": before, "after": after, "kind": kind,
            "confidence": "high", "reason": "Sửa lỗi theo ngữ cảnh gốc.",
            "evidence": evidence or []}


class StoryRepairTests(unittest.TestCase):
    def test_clean_short_source_is_scanned_but_not_needlessly_rewritten(self):
        source = "Nora visited Maisie. Luca waited outside."
        prompts = []
        def call(prompt):
            prompts.append(prompt)
            return plan()
        progress = JobProgress()
        self.assertEqual(optimize_source_script(source, call, progress), source)
        self.assertEqual(len(prompts), 1)
        self.assertTrue(prompts[0].startswith("STORY_REPAIR_PLAN"))
        report = json.loads(progress.partial_result()["optimization_review_json"])
        self.assertEqual(report["version"], OPTIMIZATION_VERSION)
        self.assertEqual(report["source_repairs"], [])

    def test_grammar_repair_is_reviewed_and_recorded_without_overwriting_source(self):
        original = "Nora were tired. Luca waited outside."
        correction = edit("Nora were tired.", "Nora was tired.")
        prompts = []
        def call(prompt):
            prompts.append(prompt)
            if prompt.startswith("STORY_REPAIR_PLAN"):
                return plan([correction])
            self.assertIn(original, prompt)
            self.assertIn("Nora was tired", prompt)
            return '{"ok":true,"issues":[]}'
        progress = JobProgress()
        result = optimize_source_script(original, call, progress)
        self.assertEqual(result, "Nora was tired. Luca waited outside.")
        self.assertEqual(original, "Nora were tired. Luca waited outside.")
        self.assertEqual(len(prompts), 2)
        report = json.loads(progress.partial_result()["optimization_review_json"])
        self.assertEqual(report["method"], "repaired_source")
        self.assertEqual(report["source_repairs"][0]["before"], correction["before"])
        self.assertEqual(report["source_repairs"][0]["after"], correction["after"])

    def test_reference_repair_requires_real_source_evidence(self):
        source = "The orderly reached for the tray. He grabbed Nora's wrist."
        correction = edit("He grabbed Nora's wrist.", "The orderly grabbed Nora's wrist.",
                          kind="reference", evidence=["The orderly reached for the tray."])
        replies = iter([plan([correction]), '{"ok":true,"issues":[]}'])
        result, changes, _ = repair_source_script(source, lambda _: next(replies), JobProgress())
        self.assertIn("The orderly grabbed Nora's wrist", result)
        self.assertEqual(len(changes), 1)

    def test_fabricated_evidence_and_duplicate_targets_are_rejected(self):
        cases = [
            ("Nora waited.", edit("Nora waited.", "Nora went home.", kind="continuity",
                                 evidence=["She decided to go home."])),
            ("He waited. He waited.", edit("He waited.", "Luca waited.")),
            ("Nora waited.", edit("Nora waited.", "Nora went home.", kind="continuity")),
        ]
        for source, correction in cases:
            with self.subTest(source=source, correction=correction):
                with self.assertRaisesRegex(ValueError, "Chưa xác minh"):
                    repair_source_script(source, lambda _: plan([correction]), JobProgress())

    def test_overlapping_edits_are_rejected(self):
        corrections = [edit("Nora were tired", "Nora was tired"), edit("were tired", "was tired")]
        with self.assertRaisesRegex(ValueError, "chồng lấn"):
            repair_source_script("Nora were tired.", lambda _: plan(corrections), JobProgress())

    def test_rejected_plot_change_is_not_applied_and_uncertainty_is_reported(self):
        original = "Nora arrived at 5:20. Nora called at 6:01."
        bad = edit("Nora called at 6:01.", "Nora called at 5:21.", kind="continuity",
                   evidence=["Nora arrived at 5:20."])
        replies = iter([
            plan([bad]), '{"ok":false,"issues":["Invented timestamp"]}',
            plan(unresolved=["Không đủ căn cứ thay mốc 6:01; không suy đoán thời gian."]),
        ])
        result, changes, unresolved = repair_source_script(original, lambda _: next(replies), JobProgress())
        self.assertEqual(result, original)
        self.assertEqual(changes, [])
        self.assertTrue(unresolved)

    def test_clean_long_text_retains_every_original_character_before_condensation(self):
        original = "Nora visited Maisie. Luca waited.\n" * 500
        prompts = []
        def call(prompt):
            prompts.append(prompt)
            return plan()
        result, changes, _ = repair_source_script(original, call, JobProgress())
        self.assertEqual(result, original)
        self.assertGreater(len(prompts), 1)
        self.assertEqual(changes, [])

    def test_manual_translation_prepares_new_policy_and_commits_only_on_success(self):
        original = "Nora were tired."
        session = {"source": original, "optimized_script": "Old summary",
                   "optimization_review_json": "{}", "translated": "Old translation"}
        correction = edit(original, "Nora was tired.")
        def prepare(current):
            replies = iter([plan([correction]), '{"ok":true,"issues":[]}'])
            return prepare_reviewed_script(current, lambda _: next(replies), JobProgress())
        previous = dict(session)
        with self.assertRaises(ValueError):
            rerun_translation(session, "vi", lambda *_: "", prepare=prepare)
        self.assertEqual(session, previous)
        seen = []
        result = rerun_translation(session, "vi", lambda text, _: seen.append(text) or "Nora mệt.", prepare=prepare)
        self.assertEqual(seen, ["Nora was tired."])
        self.assertEqual(result, "Nora mệt.")
        self.assertEqual(session["source"], original)
        self.assertEqual(session["optimized_script"], "Nora was tired.")
        self.assertEqual(prepare_reviewed_script(session, lambda _: self.fail("Already reviewed"), JobProgress()), {})


if __name__ == "__main__":
    unittest.main()

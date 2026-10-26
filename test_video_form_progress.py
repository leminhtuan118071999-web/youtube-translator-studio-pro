"""Auto-generate every voice-estimated scene and report progress."""
import json
import unittest

from video_scene_planner import narration_plan
from video_forms_ui import _completed_count, _generate_all_remaining, _progress_description


class SceneProgressTests(unittest.TestCase):
    def make_plan(self):
        # 870.24 seconds of audio, 109 clips of exactly eight seconds.
        plan = narration_plan(" ".join(["hello"] * 1400), "Tiếng Anh",
                              audio_duration_seconds=870.24)
        plan["character_bible"] = "Ala: long red jacket and dark hair."
        plan["style"] = "Hoạt hình 2D"
        return plan

    def test_one_click_generates_all_109_scenes_and_19_batches(self):
        plan = self.make_plan()
        self.assertEqual(len(plan["scenes"]), 109)
        calls = []
        progress = []
        checkpoints = []

        def ai(prompt):
            request = json.loads(prompt.split("Input scenes:\n", 1)[1])
            calls.append([row["number"] for row in request])
            return json.dumps({"scenes": [
                {"number": row["number"], "visual_prompt": "Character moves",
                 "transition_to_next": "crossfade"} for row in request
            ]})

        done = _generate_all_remaining(
            plan, ai, progress=lambda p,stage: progress.append(
                _progress_description(p,stage)[:3]),
            checkpoint=lambda p: checkpoints.append(_completed_count(p)),
        )
        self.assertEqual(done, 109)
        self.assertEqual(len(calls), 19)
        self.assertEqual(calls[0], list(range(1,7)))
        self.assertEqual(calls[-1], [109])
        self.assertEqual(checkpoints[-1], 109)
        self.assertEqual(len(checkpoints), 19)
        self.assertEqual(_progress_description(plan, "Finished")[2], 100)
        self.assertTrue(any(percent > 0 for _,_,percent in progress))
        self.assertTrue(all(scene["visual_prompt"] for scene in plan["scenes"]))

    def test_failure_keeps_completed_batches_then_resumes_without_rewriting(self):
        plan = self.make_plan()
        rounds = []
        successful = 0

        def sometimes_fails(prompt):
            nonlocal successful
            rows = json.loads(prompt.split("Input scenes:\n", 1)[1])
            numbers = [row["number"] for row in rows]
            rounds.append(numbers)
            if successful == 2:
                raise RuntimeError("Gateway unavailable")
            successful += 1
            return json.dumps({"scenes": [
                {"number": x, "visual_prompt": "Already generated scene",
                 "transition_to_next": ""} for x in numbers
            ]})

        checkpoints = []
        with self.assertRaisesRegex(RuntimeError, "Gateway unavailable"):
            _generate_all_remaining(
                plan, sometimes_fails,
                checkpoint=lambda p: checkpoints.append(_completed_count(p))
            )
        self.assertEqual(checkpoints, [6,12])
        self.assertEqual(_completed_count(plan), 12)
        self.assertEqual(rounds[-1][0], 13)

        def resumed(prompt):
            rows = json.loads(prompt.split("Input scenes:\n", 1)[1])
            return json.dumps({"scenes": [
                {"number": r["number"], "visual_prompt": "Resumed",
                 "transition_to_next": ""} for r in rows
            ]})

        _generate_all_remaining(plan, resumed)
        self.assertEqual(_completed_count(plan), 109)
        self.assertEqual(plan["scenes"][0]["visual_prompt"].endswith(
            "Already generated scene"), True)
        self.assertEqual(plan["scenes"][12]["visual_prompt"].endswith(
            "Resumed"), True)


if __name__ == "__main__":
    unittest.main()

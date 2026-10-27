"""Shared output reservations for bounded text-processing operations."""
import re


def task_output_budget(prompt):
    # Leave reasoning headroom while avoiding a large narrative budget for
    # reviews whose final output is only a short JSON verdict.
    if prompt.startswith(("FAITHFULNESS_REVIEW", "STORY_REPAIR_REVIEW")):
        return 1024
    if prompt.startswith("Write visual_prompt") and "PAIRED_SCENE_PROMPTS" in prompt[:500]:
        count = re.search(r"Create exactly (\d+)", prompt[:300])
        return min(6144, 800 + 1800 * int(count[1])) if count else 4400
    if prompt.startswith("NARRATION_TRANSLATION"):
        return 4096
    if prompt.startswith("STORY_ARC_SELECTION"):
        return 3072
    if prompt.startswith("STORY_REPAIR_PLAN"):
        return 1800
    if prompt.startswith("SOURCE_GROUNDED_SUMMARY"):
        if "TARGET_STORY_REWRITE:" in prompt[:700]:
            target = re.search(r"tối đa (\d+) ký tự", prompt[:300])
            if target:
                return min(4096, max(2048, (int(target[1]) + 1) // 2 + 700))
        return 3072
    return None

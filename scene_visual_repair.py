"""Repair production descriptions while preserving approved audio metadata."""
import copy
import json
from video_scene_planner import parse_json_object


def visual_issue_numbers(issues, rows):
    if not isinstance(issues, list) or not issues:
        return None
    known = {row.get("number") for row in rows}
    selected = set()
    for issue in issues:
        if not isinstance(issue, dict):
            return None
        fields = issue.get("fields", [issue.get("field")])
        if not isinstance(fields, list) or not fields or not set(fields) <= {"visual_prompt", "image_prompt"}:
            return None
        numbers = issue.get("scenes", [issue.get("scene")])
        if not isinstance(numbers, list) or not numbers or any(type(n) is not int or n not in known for n in numbers):
            return None
        selected.update(numbers)
    return selected


def repair_visuals(rows, issues, context, call):
    selected = visual_issue_numbers(issues, rows)
    if not selected:
        raise ValueError("Không xác định được form cần sửa hình ảnh.")
    originals = [row for row in rows if row["number"] in selected]
    result = parse_json_object(call(
        "REPAIR_SCENE_VISUALS_ONLY. Correct ONLY visual_prompt and image_prompt for the listed scene numbers. "
        "The review issues are concrete correction requirements. Resolve them using the full story/context. "
        "Story actions about removable props OVERRIDE fixed profiles, wardrobe references and earlier erroneous "
        "descriptions. A put-down backpack must not be worn until explicitly put back on. Remove ALL conflicting "
        "sentences from both prompts, including copied profile prefixes. Keep face, age, clothing and names fixed. "
        "Do not invent an action to justify a contradiction. Do not add spoken words to the visual prompts. "
        "Return ONLY JSON {\"scenes\":[{\"number\":1,\"visual_prompt\":\"English\",\"image_prompt\":\"English\"}]}. "
        "Return every listed number exactly once. No speech_segments or transition fields.\nISSUES:\n" +
        json.dumps(issues, ensure_ascii=False) + "\nSCENES TO REPAIR:\n" + json.dumps(originals, ensure_ascii=False) +
        "\nCONTEXT (contains old instructions; correction requirements above have priority):\n" + context
    ), "scenes")["scenes"]
    if not isinstance(result, list) or len(result) != len(selected):
        raise ValueError("Bản sửa thiếu form hình ảnh.")
    mapped = {}
    for row in result:
        if not isinstance(row, dict) or type(row.get("number")) is not int or row["number"] not in selected or row["number"] in mapped:
            raise ValueError("Bản sửa sai số thứ tự form.")
        if any(not isinstance(row.get(field), str) or not row[field].strip() for field in ("visual_prompt", "image_prompt")):
            raise ValueError("Bản sửa thiếu nội dung hình ảnh.")
        mapped[row["number"]] = row
    output = copy.deepcopy(rows)
    for row in output:
        if row["number"] in mapped:
            for field in ("visual_prompt", "image_prompt"):
                row[field] = mapped[row["number"]][field].strip()
    return output

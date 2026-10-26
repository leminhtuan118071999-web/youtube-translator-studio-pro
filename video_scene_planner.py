"""Plan 8-second video prompts directly from the target-language translation.

This module produces a source-locked narration plan. AI may add ONLY visual
direction; the voiceover segments, scene timings, and language remain owned by
this deterministic planner so prompt generation cannot rewrite the translation.
"""
import hashlib
import json
import math
import re

SECONDS_PER_SCENE = 8
MAX_SCENES = 240
DEFAULT_WPM = 135
TRANSITION_SECONDS = 0.4


def source_fingerprint(translation, language):
    if not isinstance(translation, str) or not isinstance(language, str):
        raise ValueError("Không có bản dịch và ngôn ngữ đích hợp lệ.")
    raw = json.dumps([translation.strip(), language.strip()], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def narration_plan(translation, language, *, words_per_minute=DEFAULT_WPM,
                   audio_duration_seconds=None):
    """Every word from the translation appears exactly once, in chronological order.

    Without audio, timing is an estimate based on speech rate. With audio,
    the scene count follows actual total audio duration, but paragraph-to-audio
    alignment is still an estimate until word timings/forced alignment exist.
    """
    if not isinstance(translation, str) or not translation.strip():
        raise ValueError("Hãy tạo bản dịch sang ngôn ngữ đích trước.")
    if not isinstance(language, str) or not language.strip():
        raise ValueError("Chưa chọn ngôn ngữ đích.")
    if len(translation) > 350000:
        raise ValueError("Bản dịch quá dài; hãy chia thành nhiều phần.")
    if not isinstance(words_per_minute, int) or not 80 <= words_per_minute <= 220:
        raise ValueError("Tốc độ đọc phải từ 80 đến 220 từ/phút.")
    if audio_duration_seconds is not None:
        if (not isinstance(audio_duration_seconds, (int, float))
                or not math.isfinite(audio_duration_seconds)
                or audio_duration_seconds <= 0):
            raise ValueError("Thời lượng giọng đọc phải là số dương hợp lệ.")

    text = re.sub(r"\s+", " ", translation).strip()
    has_words = bool(re.search(r"\s", text))
    # CJK scripts can have no word separators. Count each visible character
    # and estimate by 4 chars/s; the audio-duration option is more accurate.
    units = text.split(" ") if has_words else list(text)
    estimated_seconds = (
        len(units) * 60.0 / words_per_minute
        if has_words else len(units) / 4.0
    )
    duration = float(audio_duration_seconds) if audio_duration_seconds is not None else estimated_seconds
    count = max(1, math.ceil(duration / SECONDS_PER_SCENE))
    if count > MAX_SCENES:
        raise ValueError(
            f"Nội dung cần khoảng {count} form. Giới hạn {MAX_SCENES} "
            "form/lần để tránh tạo quá nhiều tác vụ API; hãy chia nội dung thành phần nhỏ."
        )
    # Don't create empty narration scenes even for unusually long audio.
    count = min(count, len(units))
    base, extra = divmod(len(units), count)
    out, pos = [], 0
    for index in range(count):
        size = base + (1 if index < extra else 0)
        part = (" ".join(units[pos:pos + size]) if has_words
                else "".join(units[pos:pos + size]))
        pos += size
        out.append({
            "number": index + 1,
            "start_seconds": index * SECONDS_PER_SCENE,
            "end_seconds": (index + 1) * SECONDS_PER_SCENE,
            "duration_seconds": SECONDS_PER_SCENE,
            "voiceover": part,
            "visual_prompt": "",
            "transition_to_next": "" if index == count - 1 else
                f"crossfade {TRANSITION_SECONDS:.1f}s",
        })
    if (" ".join(s["voiceover"] for s in out) if has_words
            else "".join(s["voiceover"] for s in out)) != text:
        raise AssertionError("Phân cảnh không giữ trọn bản dịch.")
    return {
        "version": 1, "language": language,
        "source_hash": source_fingerprint(translation, language),
        "seconds_per_scene": SECONDS_PER_SCENE,
        "words_per_minute": words_per_minute,
        "audio_duration_seconds": audio_duration_seconds,
        "estimated_speech_seconds": round(estimated_seconds, 2),
        "end_padding_seconds": round(max(0.0, count * SECONDS_PER_SCENE - duration), 2),
        "character_bible": "",
        "scenes": out,
    }


def parse_json_object(raw, required_field):
    if not isinstance(raw, str):
        raise ValueError("AI trả về dữ liệu không hợp lệ.")
    left, right = raw.find("{"), raw.rfind("}")
    if left < 0 or right <= left:
        raise ValueError("AI không trả về JSON của form video.")
    try:
        result = json.loads(raw[left:right + 1])
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("JSON tạo form video không hợp lệ.") from exc
    if not isinstance(result, dict) or required_field not in result:
        raise ValueError("AI thiếu trường dữ liệu form video.")
    return result


def character_bible_prompt(translation, language, style):
    """One immutable visual identity to reuse across all video form batches."""
    sample = translation if len(translation) <= 18000 else (
        translation[:11500] + "\n[...]\n" + translation[-5500:]
    )
    return (
        f"Write ONLY in {language}. Make a consistent CHARACTER/WORLD REFERENCE "
        "for a chronological video based STRICTLY on this translated text. "
        "Do not change the story or invent new story events. For each recurring "
        "person or animal, specify a fixed recognizable name, species/age when "
        "supported, appearance, clothes, colors, identifying features and "
        "behavior. If a detail is absent, choose one neutral consistent design "
        "instead of alleging the story stated it. Keep the visual style "
        f"consistent: {style}. Return JSON only with a non-empty string "
        'field: {"character_bible":"..."}. Translate all descriptions into '
        f"{language}. The reference must be concise and reusable. "
        "Source translated script:\n" + sample
    )


def batch_prompt(plan, scenes, *, style):
    """Require self-contained 8s prompts with exact voiceover and transitions."""
    basic = [{
        "number": scene["number"],
        "voiceover": scene["voiceover"],
        "time": f"{scene['start_seconds']}-{scene['end_seconds']}s",
    } for scene in scenes]
    instructions = (
        f"Write ONLY in {plan['language']}. Create exactly {len(scenes)} "
        "self-contained scene-generation prompts for an 8-second-per-scene "
        "video based STRICTLY on the provided target-language voiceover. "
        "Do not add new plot points, dialogues or narration; do not translate, "
        "reword or omit the voiceover. Each visual_prompt must cover the "
        "specific events in that scene's voiceover and describe in detail "
        "the characters' FULL fixed physical appearances, setting, actions, "
        "movements, facial expressions, camera angle/motion, lighting, visual "
        "style, ambient music and SFX with a clear 0-8 second timeline. "
        "Any character recurring in another scene MUST match exactly the "
        "immutable character reference. Design continuity of positions, "
        "props, time of day, clothing, and surroundings across neighboring "
        "scenes. No spoken dialogue beyond the provided voiceover. Every "
        "inter-scene boundary MUST include a visually seamless transition; "
        "reserve the final 0.4 second of a scene for a crossfade or match-cut "
        "into the next 8-second clip. The transition must be inside the "
        "8-second clip, not added as extra runtime. For the very last scene, "
        "return an empty transition_to_next. Return ONLY JSON: "
        '{"scenes":[{"number":1,"visual_prompt":"...","transition_to_next":"..."}]}. '
        "Do not return or modify voiceover text. The number must match "
        "each requested number exactly. Every visual_prompt and nonempty "
        "transition_to_next must be written in the TARGET language. "
        f"Visual style: {style}. Fixed character reference: "
        f"{plan['character_bible']}\nInput scenes:\n"
        + json.dumps(basic, ensure_ascii=False)
    )
    return instructions


def apply_ai_batch(plan, raw, expected_numbers):
    """Import AI visual direction only; never let AI change voiceover/timing."""
    data = parse_json_object(raw, "scenes")
    rows = data["scenes"]
    if not isinstance(rows, list) or len(rows) != len(expected_numbers):
        raise ValueError("AI trả về sai số lượng form video.")
    mapped = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("number")) is not int:
            raise ValueError("Form video thiếu số thứ tự.")
        number = row["number"]
        desc = row.get("visual_prompt")
        transition = row.get("transition_to_next")
        if (number in mapped or number not in expected_numbers
                or not isinstance(desc, str) or not desc.strip()
                or not isinstance(transition, str)):
            raise ValueError("Form AI thiếu nội dung hoặc sai số thứ tự.")
        mapped[number] = (desc.strip(), transition.strip())
    if set(mapped) != set(expected_numbers):
        raise ValueError("AI trả về sai thứ tự form video.")
    for scene in plan["scenes"]:
        if scene["number"] in mapped:
            scene["visual_prompt"], transition = mapped[scene["number"]]
            scene["transition_to_next"] = (
                transition if scene["number"] < len(plan["scenes"]) else ""
            ) or (
                f"crossfade {TRANSITION_SECONDS:.1f}s"
                if scene["number"] < len(plan["scenes"]) else ""
            )
    return plan


def plan_export_text(plan):
    pieces = [f"Video scene forms | {plan['language']} | 8s per scene",
              f"Character continuity: {plan['character_bible']}"]
    for scene in plan["scenes"]:
        pieces.append(
            f"\nScene {scene['number']:03d} — "
            f"{scene['start_seconds']:02d}-{scene['end_seconds']:02d}s "
            "(8s)\n"
            f"Voiceover: {scene['voiceover']}\n"
            f"Visual prompt: {scene['visual_prompt'] or '(not generated)'}\n"
            f"Transition: {scene['transition_to_next'] or '(end)'}"
        )
    return "\n".join(pieces)

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
TRANSITION_SECONDS = 1.0


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
    # Real audio can contain long pauses; preserve 8s silent/B-roll forms
    # rather than truncating the video when count exceeds spoken word count.
    if count > len(units) and audio_duration_seconds is None:
        raise ValueError("Kịch bản quá ngắn so với thời lượng ước lượng.")
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
    if (" ".join(s["voiceover"] for s in out if s["voiceover"]) if has_words
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
    """Detailed, named reference sheets for consistent character portraits."""
    sample = translation
    return (
        f"Write all character descriptions in {language}. CHARACTER/WORLD REFERENCE. Extract EVERY named "
        "character appearing in the following target-language story, including "
        "recurring humans and named animals, without inventing new character names. "
        "Make a production-ready, CONSISTENT visual reference sheet for EACH. "
        "Do not change the story, identity, relationships or events. "
        "Include detailed fixed face, body, eyes, hair, costume, colors, distinctive "
        "features and props, age when present, personality and scene role. "
        "If the text does NOT specify an appearance or age, choose ONE restrained "
        "neutral design for the visual adaptation and clearly identify this as "
        "a PROPOSED visual design in source_notes; NEVER present it as a story fact. "
        "Do not infer sensitive characteristics as factual when not in the text. "
        "Write a self-contained reference_prompt describing ONE full-body character "
        "on a neutral backdrop with consistent camera, full outfit and face. "
        f"Overall visual art style: {style}. "
        "Return ONLY valid JSON with nonempty character_bible and a detailed "
        "characters array of objects, one per named character, each with keys: "
        "name, description, role, species, gender, age, body, face, skin, hair, "
        "eyes, outfit, palette, accessories, signature, personality, "
        "reference_prompt, source_notes. Provide concrete detail for visual "
        "fields; use 'not specified' only when genuinely impossible to design. "
        'Example shape: {"character_bible":"Shared world and continuity", '
        '"characters":[{"name":"Ala","description":"Fixed visual identity",'
        '"role":"protagonist","species":"human","gender":"female",'
        '"age":"young adult (proposed)","body":"medium height",'
        '"face":"oval face","skin":"warm olive tone","hair":"long black braid",'
        '"eyes":"dark brown","outfit":"fixed red jacket","palette":"red, brown",'
        '"accessories":"canvas satchel","signature":"silver brooch",'
        '"personality":"thoughtful expression",'
        '"reference_prompt":"Full-body consistent portrait of Ala...",'
        '"source_notes":"Hair and coat colors are proposed; not stated"}]}. '
        "Never omit a named character to shorten the output; merge aliases of the same character. "
        "Target-language source script:\n" + sample
    )

def batch_prompt(plan, scenes, *, style):
    """Require self-contained 8s prompts with exact voiceover and transitions."""
    basic = [{
        "number": scene["number"],
        "voiceover": scene["voiceover"],
        "time": f"{scene['start_seconds']}-{scene['end_seconds']}s",
        "preceding_voiceover": next((s["voiceover"] for s in plan["scenes"] if s["number"] == scene["number"]-1), ""),
        "following_voiceover": next((s["voiceover"] for s in plan["scenes"] if s["number"] == scene["number"]+1), ""),
    } for scene in scenes]
    instructions = (
        f"Write visual_prompt and all production directions ONLY in English. Create exactly {len(scenes)} "
        "PAIRED_SCENE_PROMPTS: self-contained video and opening-frame image prompts for an 8-second-per-scene "
        "video based STRICTLY on the provided target-language voiceover. "
        "Format visual_prompt as ONE English line with explicit labeled sections separated by |: "
        "Duration: 8 seconds | Setting & Time | Character Description | Action Timeline (0-2s, 2-5s, 5-8s) | "
        "Camera & Lens | Lighting | Ambience | SFX | Music. Limit actions to what fits naturally in 8s. "
        "Use the fixed visual style and character identity; do not invent new ages, heights or wardrobe. "
        "Also return image_prompt for the SAME scene's OPENING frame only, not a collage or future action. "
        "Use one English line: Subject Description | Environment & Time | Lighting | Composition & Framing | "
        "Camera & Lens | Color Palette | Mood & Atmosphere | Effects | Negative | Aspect Ratio: 16:9. "
        "Image and video MUST use identical character appearances, clothes, props, positions, setting and light. "
        "Describe fully the characters present, with the same reference facts; do not add absent characters. "
        "The opening-frame image should contain no subtitles, watermarks or text; video subtitles are added separately. "
        "Do not add new plot points, dialogues or narration; do not translate, "
        "reword or omit the voiceover. Each visual_prompt must cover the "
        "specific events in that scene's voiceover and describe in detail "
        "If the current 8s voiceover is empty, depict a coherent silent B-roll "
        "scene grounded in adjacent narrative without inventing new events. "
        "the characters' FULL fixed physical appearances, setting, actions, "
        "movements, facial expressions, camera angle/motion, lighting, visual "
        "style, ambient music and SFX with a clear 0-8 second timeline. "
        "Any character recurring in another scene MUST match exactly the "
        "immutable character reference. Design continuity of positions, "
        "props, time of day, clothing, and surroundings across neighboring "
        "scenes. No spoken dialogue beyond the provided voiceover. Every "
        "inter-scene boundary MUST include a visually seamless transition; "
        "reserve the final 1.0 second (7-8s) of a scene for a crossfade or match-cut "
        "into the next 8-second clip. The transition must be inside the "
        "8-second clip, not added as extra runtime. For the very last scene, "
        "return an empty transition_to_next. Return ONLY JSON: "
        '{"scenes":[{"number":1,"visual_prompt":"...","image_prompt":"...","transition_to_next":"..."}]}. '
        "Also return speech_segments for each scene: an ordered array of "
        "{kind: narrator|character, speaker: exact character name or narrator, text: verbatim core words}. "
        "Concatenating segment texts in order must reproduce the FULL voiceover exactly, including punctuation. "
        "Narrative descriptions and dialogue attribution clauses belong to narrator. ONLY explicit direct speech "
        "may be assigned to a named character when source/neighbor context establishes who speaks. "
        "Do not turn reported speech into dialogue. If attribution is uncertain, keep narrator; never guess. "
        "Empty voiceover needs an empty array. Preserve quoted text and its quotation marks. "
        "Do not put spoken dialogue inside visual_prompt: use speech_segments exclusively for audio. "
        "Specify silent reactions/lip movement only for the active speaker; narrator is off screen. "
        "Subtitles are ON-SCREEN TEXT ONLY and must never be spoken a second time. "
        "Do not return or modify voiceover text. The number must match "
        "each requested number exactly. Every visual_prompt and nonempty "
        "transition_to_next must be written in English. "
        f"Spoken narration, dialogue and subtitle text MUST remain verbatim in {plan['language']}; do not translate them into English. "
        f"Visual style: {style}. Fixed character reference: "
        f"{plan['character_bible']}\nInput scenes:\n"
        + json.dumps(basic, ensure_ascii=False)
    )
    return instructions


def normalize_speech_segments(scene, segments):
    """Normalize role labels only; never infer an identity or alter spoken words."""
    if not isinstance(segments, list):
        raise ValueError("Form thiếu phần phân vai lời dẫn/lời thoại.")
    narrators = {"narrator", "narration", "voiceover", "voice-over", "người kể", "người kể chuyện", "lời dẫn", "lời kể", "dẫn chuyện", "narracja", "lektor"}
    characters = {"character", "dialogue", "dialog", "dialogue character", "nhân vật", "lời thoại", "thoại"}
    unknown = {"", "unknown", "character", "nhân vật", "không rõ", "không xác định", "speaker", "n/a", "none", "null"}
    result = []
    for item in segments:
        if not isinstance(item, dict):
            raise ValueError("Đoạn lời nói không hợp lệ.")
        kind = str(item.get("kind") or "").strip().casefold()
        speaker = item.get("speaker")
        speaker = speaker.strip() if isinstance(speaker, str) else ""
        if kind in narrators:
            result.append({**item, "kind":"narrator", "speaker":"narrator"})
        elif kind in characters:
            if speaker.casefold() in unknown or speaker.casefold() in narrators:
                result.append({**item, "kind":"narrator", "speaker":"narrator", "speaker_uncertain":True})
            else:
                result.append({**item, "kind":"character", "speaker":speaker})
        else:
            raise ValueError("Loại lời nói phải là narrator hoặc character.")
    validate_speech_segments(scene, result)
    return result


def repair_speech_segments(scene, segments, call, *, before="", after=""):
    """Repair role metadata with source offsets; never ask AI to rewrite speech."""
    try:
        return normalize_speech_segments(scene, segments)
    except ValueError as exc:
        error = str(exc)
    voice = scene.get("voiceover", "")
    if not voice.strip():
        return []
    for attempt in range(2):
        try:
            response = parse_json_object(call(
                "REPAIR_SPEECH_ROLES. Assign roles to the EXACT source string using zero-based "
                "Python character offsets (Unicode code points). End offsets are exclusive. "
                "Cover every character once, contiguously, from 0 to length; never write replacement words. "
                "Narrator handles descriptions, reported speech, attribution clauses and uncertain identities. "
                "Use character ONLY for explicit direct speech with a named speaker established by original/context. "
                "A quoted fragment may start in the previous scene; use adjacent context to keep the speaker. "
                'Return ONLY JSON {"segments":[{"start":0,"end":10,"kind":"narrator","speaker":"narrator"}]}. '
                "For character use kind=character and the exact name. No guessed names. "
                "Previous error: " + error + "\nSOURCE DATA:\n" + json.dumps(
                    dict(source=voice, length=len(voice), before=before, after=after), ensure_ascii=False)
            ), "segments")
            spans = response["segments"]
            if not isinstance(spans, list) or not spans:
                raise ValueError("Thiếu các đoạn phân vai.")
            result, position = [], 0
            for span in spans:
                if (not isinstance(span, dict) or type(span.get("start")) is not int
                        or type(span.get("end")) is not int or span["start"] != position
                        or not position < span["end"] <= len(voice)):
                    raise ValueError("Mốc phân vai phải liền mạch, đúng phạm vi câu gốc.")
                result.append(dict(kind=span.get("kind"), speaker=span.get("speaker"),
                                   text=voice[position:span["end"]]))
                position = span["end"]
            if position != len(voice):
                raise ValueError("Phân vai chưa phủ hết câu gốc.")
            return normalize_speech_segments(scene, result)
        except ValueError as exc:
            error = str(exc)
    raise ValueError("Chưa sửa được phân vai của form " + str(scene.get("number", "")) + ": " + error)


def validate_speech_segments(scene, segments):
    if not isinstance(segments, list):
        raise ValueError("Form thiếu phần phân vai lời dẫn/lời thoại.")
    for item in segments:
        if (not isinstance(item, dict) or item.get("kind") not in ("narrator", "character")
                or not isinstance(item.get("speaker"), str) or not item["speaker"].strip()
                or not isinstance(item.get("text"), str) or not item["text"].strip()
                or item["kind"] == "narrator" and item["speaker"] != "narrator"
                or item["kind"] == "character" and item["speaker"].lower() in ("narrator", "unknown", "character")):
            raise ValueError("Lời thoại phải có tên người nói; lời dẫn thuộc người kể.")
    normalize = lambda text: " ".join(text.split())
    if normalize(" ".join(item["text"] for item in segments)) != normalize(scene.get("voiceover", "")):
        raise ValueError("Phân vai làm thay đổi, lặp hoặc bỏ sót lời đọc gốc.")
    return segments


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
        image_prompt = row.get("image_prompt")
        if plan.get("paired_prompts_required") and (not isinstance(image_prompt, str) or not image_prompt.strip()):
            raise ValueError("Form thiếu Image Prompt khung hình mở đầu.")
        segments = row.get("speech_segments")
        scene_source = next((s for s in plan["scenes"] if s["number"] == number), {})
        if segments is not None or plan.get("speech_roles_required"):
            validate_speech_segments(scene_source, segments)
        mapped[number] = (desc.strip(), transition.strip(), segments, image_prompt)
    if set(mapped) != set(expected_numbers):
        raise ValueError("AI trả về sai thứ tự form video.")
    for scene in plan["scenes"]:
        if scene["number"] in mapped:
            description, transition, segments, image_prompt = mapped[scene["number"]]
            if isinstance(image_prompt, str) and image_prompt.strip():
                scene["image_prompt"] = image_prompt.strip()
            if segments is not None:
                scene["speech_segments"] = segments
            bible = plan.get("character_bible", "").strip()
            scene["visual_prompt"] = (
                description if not bible or bible in description
                else bible + "\n\n" + description
            )
            # Always enforce a 1-second boundary within each 8s clip.
            # A provider cannot silently replace it with a different timing.
            scene["transition_to_next"] = (
                f"crossfade {TRANSITION_SECONDS:.1f}s"
                if scene["number"] < len(plan["scenes"]) else ""
            )
    return plan


def add_scene_subtitles(plan):
    """Use the locked target-language narration as each scene's subtitle."""
    for scene in plan.get("scenes", []):
        if isinstance(scene, dict):
            scene["subtitle"] = str(scene.get("voiceover", "") or "")
    return plan


def plan_export_text(plan):
    pieces = [f"Video scene forms | English instructions | Spoken/subtitle language: {plan['language']} | 8s per scene",
              f"Character continuity: {plan['character_bible']}"]
    for scene in plan["scenes"]:
        pieces.append(
            f"\nScene {scene['number']:03d} — "
            f"{scene['start_seconds']:02d}-{scene['end_seconds']:02d}s "
            "(8s)\n"
            f"Voiceover: {scene['voiceover']}\n"
            f"Subtitle: {scene['voiceover']}\n"
            f"Visual prompt: {scene['visual_prompt'] or '(not generated)'}\n"
            f"Transition: {scene['transition_to_next'] or '(end)'}"
        )
    return "\n".join(pieces)


def continuous_video_forms_text(plan):
    """Compact, copy-ready 8-second scene prompts separated by a blank line.

    Keep the full scene prompt (including consistent character descriptions),
    narration in the selected target language, and cut instructions. Only
    remove redundant field names/global timecodes; never summarize or alter
    the generated visual instructions.
    """
    blocks = []
    for scene in plan.get("scenes", []):
        if not isinstance(scene, dict) or not str(scene.get("visual_prompt", "")).strip():
            continue
        number = int(scene["number"])
        visual = " ".join(scene["visual_prompt"].split())
        voice = " ".join(str(scene.get("voiceover", "")).split())
        transition = " ".join(str(scene.get("transition_to_next", "")).split())
        vietnamese = False  # Production instructions are English; spoken/subtitle text stays source-locked.
        voice_label = "Lời đọc" if vietnamese else "Voice"
        subtitle_label = "Phụ đề trên màn hình" if vietnamese else "Subtitle (on screen, target language)"
        next_label = "Chuyển cảnh" if vietnamese else "Next"
        if vietnamese:
            transition = transition.replace("crossfade", "mờ chồng")
        block = f"{number:02d} | 8s | {visual}"
        if plan.get("language"):
            block += f" | Spoken/subtitle language: {plan['language']} (keep supplied text verbatim)"
        segments = scene.get("speech_segments")
        if isinstance(segments, list):
            validate_speech_segments(scene, segments)
            rules = ("Âm thanh theo đúng thứ tự; người kể đọc ngoài hình, nhân vật chỉ nói câu được gán; "
                     "các nhân vật khác im lặng. Phụ đề chỉ hiển thị chữ, không đọc lại." if vietnamese else
                     "Audio in the listed order. Narrator is off-screen; only the named character speaks each assigned line. "
                     "Other characters remain silent. Subtitles are display-only, never read aloud again.")
            block += " | " + rules
            for item in segments:
                label = (("Lời dẫn — người kể" if vietnamese else "Narrator (off-screen)") if item["kind"] == "narrator"
                         else ("Lời thoại — " if vietnamese else "Dialogue — ") + item["speaker"])
                block += f" | {label}: {item['text']}"
        else:
            block += f" | {voice_label}: {voice}"
            block += " | Chưa phân vai lời nói" if vietnamese else " | Speech roles not assigned"
        if voice:
            block += f" | {subtitle_label}: {voice}"
        if transition:
            block += f" | {next_label}: {transition}"
        blocks.append(block)
    return "\n\n".join(blocks)


def continuous_image_prompts_text(plan):
    return "\n\n".join(
        f"{int(s['number']):02d} | " + " ".join(s["image_prompt"].split())
        for s in plan.get("scenes", [])
        if isinstance(s, dict) and isinstance(s.get("image_prompt"), str) and s["image_prompt"].strip()
    )


VIDEO_FORMS_PER_PANEL = 99


def grouped_video_forms(plan, group_size=VIDEO_FORMS_PER_PANEL):
    """Return nonempty 99-slot ranges, preserving original scene numbers.

    Boundaries are based on the scene's sequence position, NOT the number of
    completed prompts: scenes 1-99 belong in panel 1, 100-198 in panel 2.
    Incomplete slots are omitted from the copied text, without shifting a
    later scene into an earlier panel.
    """
    if not isinstance(group_size, int) or group_size <= 0:
        raise ValueError("Mỗi ô phải chứa số lượng form dương.")
    scenes = plan.get("scenes", [])
    if not isinstance(scenes, list):
        raise ValueError("Danh sách form không hợp lệ.")
    result = []
    for start in range(0, len(scenes), group_size):
        chunk = scenes[start:start + group_size]
        filled = [scene for scene in chunk if isinstance(scene, dict)
                  and str(scene.get("visual_prompt", "")).strip()]
        if not filled:
            continue
        content = continuous_video_forms_text({"scenes": filled, "language": plan.get("language", "")})
        result.append({
            "panel": start // group_size + 1,
            "first": start + 1,
            "last": min(start + group_size, len(scenes)),
            "completed": len(filled),
            "content": content,
            "image_content": continuous_image_prompts_text({"scenes": filled}),
        })
    return result

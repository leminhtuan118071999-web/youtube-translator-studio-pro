"""Optional timestamp-aware alignment of translated narration to uploaded speech.

Uses OpenAI Whisper word timestamps when explicitly given an OpenAI API key.
Without the key, the caller may use duration-only planning with an honest
approximation warning. The uploaded audio is never retained by this module.
"""
import difflib
import math
import re

import requests

MAX_AUDIO_BYTES = 25 * 1024 * 1024


def _tokens(text):
    return re.findall(r"[^\W_]+", str(text).casefold(), flags=re.UNICODE)


def whisper_word_timestamps(audio_bytes, filename, api_key):
    """Transcribe the actual uploaded voice recording, obtaining word timings."""
    if not isinstance(audio_bytes, bytes) or not audio_bytes or len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValueError("File giọng đọc phải dưới 25 MB để phân tích timestamp.")
    if not api_key:
        raise ValueError("Thiếu OpenAI API key để căn lời đọc từng từ.")
    response = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": (filename, audio_bytes)},
        data={
            "model": "whisper-1", "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        },
        timeout=240,
    )
    if not response.ok:
        raise ValueError(
            f"Không lấy được mốc lời đọc từ API âm thanh (HTTP {response.status_code}). "
            "Kiểm tra định dạng âm thanh, quyền API và dung lượng file."
        )
    try:
        data = response.json()
        words = data["words"]
        if not isinstance(words, list) or not words:
            raise ValueError("Không nhận được mốc thời gian từng từ.")
        result = []
        for word in words:
            token, start, end = word["word"], float(word["start"]), float(word["end"])
            if not token or not math.isfinite(start) or not math.isfinite(end):
                raise ValueError("Dữ liệu timestamp có lỗi.")
            if start < 0 or end < start:
                raise ValueError("Dữ liệu timestamp không theo thứ tự.")
            result.append({"word": str(token), "start": start, "end": end})
        if any(result[i]["start"] < result[i - 1]["start"] for i in range(1, len(result))):
            raise ValueError("Mốc lời đọc không tăng dần.")
        return result
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("API không trả về timestamp từng từ hợp lệ.") from exc


def align_target_words(translation, stamped_words, duration):
    """Map word boundaries to audio by lexical anchors; preserve source words.

    Reject material transcription mismatches instead of claiming false sync.
    Returns estimated per-token audio positions. Whisper timestamps are
    measurement of the recognized voice, not a guaranteed forced alignment.
    """
    if not stamped_words or not duration or duration <= 0:
        raise ValueError("Thiếu giọng đọc hoặc timestamp.")
    source = translation.split()
    heard = [str(row.get("word", "")) for row in stamped_words]
    if not source or not heard:
        raise ValueError("Không đủ từ để căn giọng đọc.")
    normalize = lambda w: "".join(_tokens(w))
    a, b = [normalize(w) for w in source], [normalize(w) for w in heard]
    similarity = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    if similarity < 0.72:
        raise ValueError(
            f"Giọng đọc khác nhiều so với bản dịch (độ tương đồng {similarity:.0%}). "
            "Hãy tải file đọc đúng bản dịch, tránh căn sai cảnh."
        )
    matches = difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
    anchors = [(i + shift, float(stamped_words[j + shift]["start"]))
               for i, j, length in matches for shift in range(length)]
    if not anchors:
        raise ValueError("Không tìm được từ tương ứng giữa bản dịch và âm thanh.")
    anchors = [(-1, 0.0)] + anchors + [(len(source), float(duration))]
    stamps = []
    for left, right in zip(anchors, anchors[1:]):
        ai, at = left
        bi, bt = right
        for index in range(ai + 1, bi + 1):
            if index < len(source):
                fraction = (index - ai) / (bi - ai)
                stamps.append(min(float(duration), max(0.0, at + fraction * (bt - at))))
    if len(stamps) != len(source):
        raise AssertionError("Alignment did not preserve source tokens.")
    return stamps, round(similarity, 3)


def audio_aligned_plan(translation, language, duration, word_positions):
    """Create 8-second time windows based on timestamps, never rewrite the script."""
    from video_scene_planner import (
        narration_plan, SECONDS_PER_SCENE, MAX_SCENES, TRANSITION_SECONDS,
    )
    if len(word_positions) != len(translation.split()):
        raise ValueError("Mốc giọng đọc không trùng số từ của bản dịch.")
    base = narration_plan(
        translation, language, audio_duration_seconds=duration,
    )
    # Need an 8-second clip even when the final portion is mostly silence.
    tokens = translation.split()
    boundaries = []
    index = 0
    for scene in base["scenes"]:
        cutoff = scene["end_seconds"]
        end = index
        while end < len(tokens) and word_positions[end] < cutoff:
            end += 1
        boundaries.append((index, end))
        index = end
    if index < len(tokens):
        boundaries[-1] = (boundaries[-1][0], len(tokens))
    # Silence may produce empty 8s windows. These are intentional B-roll
    # scenes with no extra spoken dialogue.
    for scene, (first, last) in zip(base["scenes"], boundaries):
        scene["voiceover"] = " ".join(tokens[first:last])
    if " ".join(s["voiceover"] for s in base["scenes"]).strip() != " ".join(tokens):
        raise AssertionError("Aligned video forms lost a piece of narration.")
    base["alignment_mode"] = "whisper_word_timestamps"
    return base

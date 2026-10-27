"""Background worker for YouTube Translator Studio Pro.

Never import Streamlit or touch st.session_state from a worker thread.
Jobs and API keys exist in process memory, not persistent storage.
"""
import json
import re
import threading
import time
from urllib.parse import urlsplit

import requests
from youtube_transcript_api import YouTubeTranscriptApi

from api_clients import RateLimitError, TransientProviderError, generate_text
from groq_pacing import groq_request_gate
from faithful_summary import (optimize_source_script, MAX_OPTIMIZED_SCRIPT_CHARS,
                              COMPATIBLE_OPTIMIZATION_VERSIONS, source_hash, translate_part_faithfully,
                              rewrite_target_script, MAX_TARGET_SCRIPT_CHARS)
from transcript_sources import fetch_with_fallback
from video_scene_planner import (narration_plan, character_bible_prompt, batch_prompt, parse_json_object, apply_ai_batch)
from character_images import IMAGE_STORE, character_specs, create_character_png, IMAGE_MODEL


class JobProgress:
    def __init__(self):
        self._lock = threading.Lock()
        self._fraction = 0
        self._stage = "Đang chờ..."
        self._cancel = threading.Event()
        self._fields = {}

    def update(self, fraction, stage):
        with self._lock:
            self._fraction = max(self._fraction, min(100, int(fraction)))
            self._stage = str(stage)[:140]

    def snapshot(self):
        with self._lock:
            return self._fraction, self._stage

    def publish(self, field, value):
        """Share partial, non-sensitive output safely with the UI."""
        with self._lock:
            self._fields[field] = value

    def partial_result(self):
        with self._lock:
            return dict(self._fields)

    def cancel(self):
        self._cancel.set()

    def check_cancelled(self):
        if self._cancel.is_set():
            raise RuntimeError("Tác vụ đã bị hủy.")


def youtube_id(url):
    match = re.search(
        r"(?:v=|youtu\.be/|/shorts/|/live/)([\w-]{11})",
        url or "",
    )
    return match.group(1) if match else None


def fetch_subtitles(video_id, supadata_key="", progress=None):
    """Attempt native YouTube subtitles, then a configured transcription service."""
    text, language, provider_name = fetch_with_fallback(
        video_id, supadata_key=supadata_key, progress=progress
    )
    if progress:
        progress.update(9, f"✅ Lấy phụ đề thành công ({provider_name}).")
    return text, language


def chunk_text(text, limit=5500):
    start = 0
    while start < len(text):
        end = min(len(text), start + limit)
        if end < len(text):
            a = text.rfind("\n", start + limit // 2, end)
            b = text.rfind(". ", start + limit // 2, end)
            if max(a, b) > start:
                end = max(a, b) + 1
        yield text[start:end]
        start = end


def parse_object(value, field):
    beginning, ending = value.find("{"), value.rfind("}")
    if beginning < 0 or ending < beginning:
        raise ValueError("AI không trả về JSON hợp lệ. Có thể cần thử lại mục này.")
    try:
        data = json.loads(value[beginning:ending + 1])
    except ValueError as exc:
        raise ValueError("AI trả về JSON không hợp lệ; hãy thử lại.") from exc
    if not isinstance(data, dict) or field not in data:
        raise ValueError("AI trả về thiếu dữ liệu cần thiết; hãy thử lại.")
    return data


def overview(text, call, progress):
    """Keep story context under the 8K TPM ceiling with hierarchical summaries."""
    max_brief = 7000
    if len(text) <= max_brief:
        return text

    pieces = list(chunk_text(text, 6000))
    summaries = []
    for idx, section in enumerate(pieces, 1):
        progress.check_cancelled()
        summaries.append(call(
            "Summarize events, named characters, settings and visual details of "
            "this part in 80-130 words. Keep chronology. Do not invent facts. "
            f"Part {idx}/{len(pieces)}:\n" + section
        ))
    combined = "\n".join(
        f"Part {idx}: {value}"
        for idx, value in enumerate(summaries, 1)
    )
    # Cover every part of long videos without sending a >8K TPM single
    # request to Groq. Each condensation uses bounded input and output.
    for _ in range(5):
        if len(combined) <= max_brief:
            return combined
        progress.check_cancelled()
        groups = list(chunk_text(combined, 6000))
        short = []
        for idx, group in enumerate(groups, 1):
            short.append(call(
                "Condense the following ordered plot beats into at most 100 words "
                "while retaining main characters, changes, and the chronological "
                f"events. Do not invent facts. Group {idx}/{len(groups)}:\n"
                + group
            ))
        updated = "\n".join(short)
        if len(updated) >= len(combined):
            break
        combined = updated
    if len(combined) > 9000:
        raise ValueError(
            "Không thể tóm tắt toàn bộ video vừa giới hạn token của model. "
            "Hãy thử model có hạn mức lớn hơn."
        )
    return combined



def run_full_job(snapshot, progress):
    """Return completed/partial fields. Never return or store the API key."""
    result = {"ok": False, "fields": {}, "error": ""}
    fields = result["fields"]
    # Resume only checkpoints created by an earlier lease holder of this
    # SAME queue job, not arbitrary session results from another run.
    old_fields = snapshot.get("resume_fields") or {}
    if isinstance(old_fields, dict):
        fields.update({name:value for name,value in old_fields.items()
                       if name in ("source","title","caption_language",
                                   "optimized_script","optimization_review_json","optimization_work_json","translation_parts",
                                   "translation_complete","translated",
                                   "character_bible","character_profile",
                                   "character_images_manifest","character_images_error",
                                   "new_title","new_description","seo_tags",
                                   "metadata","language")})
    api_key = snapshot["api_key"]

    def _wait_for_retry(seconds, description):
        """Keep the existing job cancelable while its progress shows the wait."""
        remaining = max(0.0, float(seconds))
        while remaining > 0:
            progress.check_cancelled()
            pct, _ = progress.snapshot()
            progress.update(pct, f"{description} ({int(remaining + 0.99)} giây)...")
            step = min(1.0, remaining)
            time.sleep(step)
            remaining -= step

    def call(prompt):
        """Retry only the failed request; never repeat finished translation chunks."""
        rate_attempt = 0
        upstream_attempt = 0
        while True:
            progress.check_cancelled()
            try:
                # Coordinate TPM pacing with other Streamlit jobs using Groq.
                with groq_request_gate.reporting(progress):
                    if snapshot["provider"] == "API bên thứ ba (tùy chỉnh)":
                        return generate_text(
                            snapshot["provider"], snapshot["base_url"],
                            snapshot["model"], api_key, prompt,
                            api_format=snapshot.get("api_format", "chat"),
                            auth_mode=snapshot.get("auth_mode", "bearer"),
                        )
                    return generate_text(
                        snapshot["provider"], snapshot["base_url"],
                        snapshot["model"], api_key, prompt
                    )
            except RateLimitError as exc:
                if not exc.can_retry:
                    raise RuntimeError(
                        "Tài khoản API đã hết hạn mức trong ngày hoặc quota "
                        "của model bằng 0. Kiểm tra giới hạn model trong "
                        "bảng điều khiển nhà cung cấp, chọn model khả dụng "
                        "hoặc chờ nhà cung cấp cấp lại quota. " + str(exc)
                    ) from exc
                if rate_attempt >= 6:
                    raise RuntimeError(
                        "Đã tự động thử lại 6 lần nhưng API vẫn vượt giới hạn "
                        "tốc độ hoặc quota. Các kết quả đã xong được giữ lại. "
                        "Hãy thử lại sau hoặc chọn model khác. " + str(exc)
                    ) from exc
                rate_attempt += 1
                pause = min(120.0, max(2.0, float(exc.retry_after or 30.0) + 3))
                _wait_for_retry(
                    pause,
                    f"⏳ API {snapshot['provider']} giới hạn tốc độ: "
                    f"tự thử lại {rate_attempt}/6",
                )
            except TransientProviderError as exc:
                # Only retry a temporary upstream failure, not bad credentials,
                # unsupported models, or client errors. Limit duplicate POSTs
                # because a failed gateway response may hide a successful billable
                # request upstream.
                if upstream_attempt >= 3:
                    raise RuntimeError(
                        "Gateway/dịch vụ AI phía sau vẫn gặp lỗi HTTP "
                        f"{exc.status_code} sau 3 lần thử lại. "
                        "Các kết quả đã xong được giữ lại. "
                        "Đây có thể là sự cố bên nhà cung cấp; "
                        "hãy thử lại sau hoặc chọn API khác. " + str(exc)
                    ) from exc
                upstream_attempt += 1
                pause = min(
                    40.0,
                    max(
                        2.0,
                        float(exc.retry_after)
                        if exc.retry_after is not None
                        else 3.0 * (2 ** (upstream_attempt - 1)),
                    ),
                )
                _wait_for_retry(
                    pause,
                    f"⏳ Gateway HTTP {exc.status_code}: "
                    f"thử lại {upstream_attempt}/3",
                )

    try:
        progress.check_cancelled()
        source = fields.get("source") or snapshot.get("source", "")
        vid = youtube_id(snapshot.get("url", ""))
        title = snapshot.get("title", "")
        description = snapshot.get("description", "")
        language = snapshot["language"]
        provided_source = (snapshot.get("uploaded_source") or "").strip()
        if vid:
            if isinstance(fields.get("source"),str) and fields["source"].strip():
                source = fields["source"]
                caption_lang = fields.get("caption_language", "Phụ đề đã lưu")
                progress.update(8, "📄 Tiếp tục với phụ đề đã lưu từ phiên trước")
            elif provided_source:
                progress.update(6, "📄 Dùng file phụ đề đã tải lên...")
                source, caption_lang = provided_source, "Phụ đề tải lên"
            else:
                progress.update(5, "📥 Đang lấy phụ đề YouTube...")
                source, caption_lang = fetch_subtitles(
                    vid, supadata_key=snapshot.get("supadata_key", ""),
                    progress=progress
                )
            fields["source"] = source
            progress.publish("source", source)
            fields["caption_language"] = str(caption_lang)
            if not title:
                try:
                    response = requests.get(
                        "https://www.youtube.com/oembed",
                        params={"url": f"https://www.youtube.com/watch?v={vid}",
                                "format": "json"}, timeout=8
                    )
                    if response.ok:
                        title = str(response.json().get("title", "")).strip()
                except (requests.RequestException, ValueError):
                    pass
            if title:
                fields["title"] = title
                progress.publish("title", title)
        if provided_source and not vid:
            source = provided_source
        if not source.strip():
            raise ValueError("Không có nội dung phụ đề để dịch.")
        if len(source) > 350000:
            raise ValueError("Phụ đề quá dài (hơn 350.000 ký tự).")
        fields["source"] = source
        progress.publish("source", source)

        # Translate the complete original as reviewed spoken narration.
        target_text = fields.get("optimized_script")
        try:
            review = json.loads(fields.get("optimization_review_json") or "{}")
        except (TypeError, ValueError):
            review = {}
        verified_checkpoint = (
            isinstance(target_text, str) and bool(target_text.strip())
            and isinstance(review, dict)
            and review.get("version") == 1
            and review.get("method") == "full_narration_translation"
            and review.get("target_language") == language
            and review.get("source_sha256") == source_hash(source)
            and review.get("output_sha256") == source_hash(target_text)
        )
        if not verified_checkpoint:
            for field in ("translation_parts", "translation_complete", "translated",
                          "character_bible", "character_profile", "character_profile_json",
                          "character_images_manifest", "character_images_error",
                          "new_title", "new_description", "seo_tags", "metadata"):
                fields.pop(field, None)
            if fields.get("optimization_work_json"):
                progress.publish("optimization_work_json", fields["optimization_work_json"])
            target_text = rewrite_target_script(source, language, call, progress)
            fields["optimization_review_json"] = progress.partial_result().get("optimization_review_json", "")
        else:
            progress.update(67, "✅ Đã khôi phục bản viết lại ngôn ngữ đích đã đối soát")
        if not target_text.strip():
            raise ValueError("Bản dịch giọng đọc không được rỗng.")
        fields.update(optimized_script=target_text, translated=target_text,
                      optimization_work_json="", translation_parts=[target_text],
                      translation_complete=True)
        for name in ("optimization_review_json", "optimization_work_json", "optimized_script",
                     "translated", "translation_parts", "translation_complete"):
            progress.publish(name, fields.get(name, ""))

        fields["language"] = language
        progress.publish("language", language)
        # Complete metadata in the same target language after narration succeeds.
        if not all(isinstance(fields.get(k), str) and fields[k].strip()
                   for k in ("new_title", "new_description", "seo_tags")):
            progress.update(96, "📝 Đang dịch tiêu đề, mô tả và từ khóa SEO...")
            brief = overview(target_text, call, progress) if not title or not description else ""
            errors = ""
            for attempt in range(2):
                try:
                    data = parse_object(call(
                        f"TARGET_METADATA. Write ONLY in {language}, preserving proper names. "
                        "Translate the supplied original title and description faithfully; "
                        "preserve their meaning, factual claims, numbers and existing links. "
                        "If either is absent, create that missing field from the story context. "
                        "Also provide 15 relevant SEO keywords in the target language. "
                        "Do not invent events, exaggerate claims or add commentary. "
                        'Return ONLY JSON {"title":"...","description":"...","tags":["..."]}. '
                        "Previous validation errors: " + errors + "\nSOURCE DATA:\n" +
                        json.dumps({"original_title": title, "original_description": description,
                                    "story_context": brief}, ensure_ascii=False)
                    ), "title")
                    values = (data.get("title"), data.get("description"), data.get("tags"))
                    if (any(not isinstance(v, str) or not v.strip() for v in values[:2])
                            or not isinstance(values[2], list) or not values[2]
                            or any(not isinstance(t, str) or not t.strip() for t in values[2])):
                        raise ValueError("Tiêu đề, mô tả hoặc danh sách từ khóa SEO bị thiếu/sai định dạng.")
                    new_title, new_description = (v.strip() for v in values[:2])
                    tags = ", ".join(t.strip() for t in values[2])
                    break
                except ValueError as exc:
                    errors = str(exc)
            else:
                raise ValueError("Chưa dịch được tiêu đề, mô tả và SEO: " + errors)
            fields.update(new_title=new_title, new_description=new_description,
                          seo_tags=tags, metadata="\n\n".join((new_title, new_description, tags)))
            for name in ("new_title", "new_description", "seo_tags", "metadata"):
                progress.publish(name, fields[name])
        result["ok"] = True
        progress.update(100, "✅ Hoàn thành bản dịch giọng đọc, tiêu đề, mô tả và SEO")
        return result

    except Exception as exc:
        pending_optimization = progress.partial_result().get("optimization_work_json", "")
        if pending_optimization:
            fields["optimization_work_json"] = pending_optimization
        # Redact credentials in provider error messages.
        safe_error = str(exc).replace(api_key, "[API KEY ĐÃ ẨN]")
        extra_key = snapshot.get("supadata_key", "")
        if extra_key:
            safe_error = safe_error.replace(extra_key, "[KEY PHỤ ĐỀ ĐÃ ẨN]")
        result["error"] = safe_error[:700]
        progress.update(100, "⚠️ Tác vụ kết thúc nhưng có lỗi.")
    return result

"""Background worker for YouTube Translator Studio Pro.

Never import Streamlit or touch st.session_state from a worker thread.
Jobs and API keys exist in process memory, not persistent storage.
"""
from youtube_metadata import generate_youtube_metadata
from processing_metrics import ProcessingMetrics
import json
import re
import threading
import time
from urllib.parse import urlsplit

import requests
from youtube_transcript_api import YouTubeTranscriptApi

from api_clients import RateLimitError, TransientProviderError, generate_text
from provider_retries import transient_retry_delay
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


def overview(text, call, progress, *, context_limit=7000):
    """Keep story context under the 8K TPM ceiling with hierarchical summaries."""
    max_brief = max(7000, min(24000, context_limit))
    piece_limit = max_brief - 1000
    if len(text) <= max_brief:
        return text

    pieces = list(chunk_text(text, piece_limit))
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
        groups = list(chunk_text(combined, piece_limit))
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
    if len(combined) > max_brief + 2000:
        raise ValueError(
            "Không thể tóm tắt toàn bộ video vừa giới hạn token của model. "
            "Hãy thử model có hạn mức lớn hơn."
        )
    return combined



def metadata_for_job(text, title, description, language, call, progress, *, fast=False, context_limit=7000):
    identity = source_hash(json.dumps([text, title, description, language, "faithful-title-hook-v1", fast, context_limit], ensure_ascii=False))
    try:
        work = json.loads(progress.partial_result().get('seo_work_json') or '{}')
    except (ValueError, TypeError):
        work = {}
    if not isinstance(work, dict) or work.get('identity') != identity:
        work = {}
    brief = work.get('context')
    if not isinstance(brief, str) or not brief:
        report = progress.partial_result().get('optimization_review_json')
        try:report = json.loads(report or '{}')
        except (ValueError,TypeError):report = {}
        if not isinstance(report,dict):report = {}
        contexts = report.get('seo_contexts')
        if (report.get('output_sha256') == source_hash(text) and report.get('target_language') == language
                and isinstance(contexts,list) and contexts and len(contexts)==report.get('reviewed_parts')
                and all(isinstance(v,str) and 0<len(v)<=1800 for v in contexts)):
            brief = overview('\n\n'.join(contexts), call, progress, context_limit=context_limit)
        else:
            brief = overview(text, call, progress, context_limit=context_limit)
    def checkpoint(candidate):
        progress.publish('seo_work_json', json.dumps(dict(identity=identity, context=brief, candidate=candidate), ensure_ascii=False))
    progress.update(97, 'Đang tạo và đối chiếu SEO; tự khôi phục kết quả đã lưu khi cần')
    result = generate_youtube_metadata(brief, title, description, language, call,
                                      resume_candidate=work.get('candidate'), checkpoint=checkpoint, self_check_only=fast)
    progress.publish('seo_work_json', '')
    return result


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
    metrics = ProcessingMetrics(progress)

    def _wait_for_retry(seconds, description):
        """Keep the existing job cancelable while its progress shows the wait."""
        wait_started = time.monotonic()
        remaining = max(0.0, float(seconds))
        while remaining > 0:
            progress.check_cancelled()
            pct, _ = progress.snapshot()
            progress.update(pct, f"{description} ({int(remaining + 0.99)} giây)...")
            step = min(1.0, remaining)
            time.sleep(step)
            remaining -= step
        metrics.retry_wait(time.monotonic()-wait_started)

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
                        return metrics.measure(prompt, lambda: generate_text(
                            snapshot["provider"], snapshot["base_url"],
                            snapshot["model"], api_key, prompt,
                            api_format=snapshot.get("api_format", "chat"),
                            auth_mode=snapshot.get("auth_mode", "bearer"),
                        ))
                    return metrics.measure(prompt, lambda: generate_text(
                        snapshot["provider"], snapshot["base_url"],
                        snapshot["model"], api_key, prompt
                    ))
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
                if exc.status_code not in (502, 503, 504):
                    raise
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
                pause = transient_retry_delay(upstream_attempt - 1, exc.retry_after)
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
            if provided_source:
                progress.update(6, "📄 Dùng nội dung nhập hoặc phụ đề tải lên...")
                source, caption_lang = provided_source, "Nội dung được cung cấp"
            elif isinstance(fields.get("source"),str) and fields["source"].strip():
                source = fields["source"]
                caption_lang = fields.get("caption_language", "Phụ đề đã lưu")
                progress.update(8, "📄 Tiếp tục với phụ đề đã lưu từ phiên trước")
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

        if snapshot.get('translation_mode') == 'direct':
            from direct_translation import translate_direct, METHOD
            target_text=fields.get('translated')
            try:report=json.loads(fields.get('optimization_review_json') or '{}')
            except (ValueError,TypeError):report={}
            valid=(isinstance(report,dict) and report.get('method')==METHOD
                   and report.get('source_sha256')==source_hash(source) and report.get('target_language')==language
                   and isinstance(target_text,str) and bool(target_text.strip())
                   and report.get('output_sha256')==source_hash(target_text))
            if not valid:
                target_text=translate_direct(source,language,call,progress)
                fields['optimization_review_json']=progress.partial_result().get('optimization_review_json','')
            fields.update(translated=target_text,optimized_script=target_text,translation_parts=[target_text],
                          translation_complete=True,optimization_work_json='')
            for name in ('optimization_review_json','optimization_work_json','translated','optimized_script','translation_parts','translation_complete'):
                progress.publish(name,fields.get(name,''))
        else:
            # Translate the complete original as reviewed spoken narration.
            target_text = fields.get("optimized_script")
            try:
                review = json.loads(fields.get("optimization_review_json") or "{}")
            except (TypeError, ValueError):
                review = {}
            verified_checkpoint = (
                isinstance(target_text, str) and bool(target_text.strip())
                and isinstance(review, dict)
                and review.get("version") == 2
                and review.get("narration_style") == "single_narrator_indirect_v1"
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
        progress.update(96, "✅ Bản dịch đã lưu; đang xử lý tiêu đề, mô tả và tag...")
        new_title, new_description, tags = metadata_for_job(
            target_text, title, description, language, call, progress, fast=snapshot.get("translation_mode")=="direct",
        )
        fields.update(new_title=new_title, new_description=new_description,
                      seo_tags=tags, metadata="\n\n".join((new_title, new_description, tags)))
        for name in ("new_title", "new_description", "seo_tags", "metadata"):
            progress.publish(name, fields[name])
        result["ok"] = True
        progress.update(100, "✅ Hoàn thành bản dịch, tiêu đề, mô tả và tag")
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
    finally:
        metrics.publish()
        result["fields"]["processing_metrics"] = progress.partial_result().get("processing_metrics", {})
    return result

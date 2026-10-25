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
from transcript_sources import fetch_with_fallback


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
                    return generate_text(
                        snapshot["provider"], snapshot["base_url"],
                        snapshot["model"], api_key, prompt
                    )
            except RateLimitError as exc:
                if not exc.can_retry:
                    raise RuntimeError(
                        "Tài khoản API đã hết giới hạn trong ngày. "
                        "Cần chờ ngày mới hoặc dùng nhà cung cấp/model khác. "
                        + str(exc)
                    ) from exc
                if rate_attempt >= 6:
                    raise RuntimeError(
                        "Đã tự động thử lại 6 lần nhưng API vẫn vượt giới hạn "
                        "token/phút. Các kết quả đã xong được giữ lại. "
                        "Hãy thử lại sau hoặc chọn model khác. " + str(exc)
                    ) from exc
                rate_attempt += 1
                pause = min(120.0, max(2.0, float(exc.retry_after or 30.0) + 3))
                _wait_for_retry(
                    pause,
                    f"⏳ Groq giới hạn TPM: tự thử lại {rate_attempt}/6",
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
        source = snapshot.get("source", "")
        vid = youtube_id(snapshot.get("url", ""))
        title = snapshot.get("title", "")
        description = snapshot.get("description", "")
        language = snapshot["language"]
        provided_source = (snapshot.get("uploaded_source") or "").strip()
        if vid:
            if provided_source:
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

        # Smaller chunks for Groq Free (8K TPM): each request needs far
        # fewer input and reserved completion tokens.
        chunk_size = (
            2200 if snapshot.get("provider") == "Groq"
            and snapshot.get("model") in ("openai/gpt-oss-20b", "openai/gpt-oss-120b")
            else 5500
        )
        chunks = list(chunk_text(source, chunk_size))
        translations = []
        for idx, part in enumerate(chunks, 1):
            progress.check_cancelled()
            progress.update(12 + int(52 * (idx - 1) / len(chunks)),
                            f"🌍 Đang dịch phần {idx}/{len(chunks)} sang {language}...")
            translation = call(
                f"Dịch chính xác toàn bộ đoạn {idx}/{len(chunks)} sang {language}. "
                "Viết tự nhiên, không thiếu câu, không thêm tình tiết, giữ tên nhân vật "
                "và xuống dòng. CHỈ xuất bản dịch.\n\n" + part
            )
            translations.append(translation)
            fields["translated"] = "\n\n".join(translations)
            progress.publish("translated", fields["translated"])

        progress.update(66, "🎨 Đang tạo 20 prompt ảnh...")
        brief = overview(fields["translated"], call, progress)
        prompts_result = parse_object(call(
            f"Hãy viết ĐÚNG 20 prompt hình ảnh điện ảnh bằng {language}, "
            "theo mạch truyện từ đầu đến cuối, các nhân vật thống nhất, không bịa. "
            'Chỉ trả JSON {"prompts":["..."]} gồm 20 chuỗi.\n\n' + brief
        ), "prompts")
        prompts = prompts_result["prompts"]
        if not isinstance(prompts, list) or len(prompts) != 20:
            raise ValueError("AI chưa trả đủ 20 prompt. Có thể chạy lại phần prompt.")
        prompts = [str(p).strip() for p in prompts]
        if any(not p for p in prompts):
            raise ValueError("Có prompt ảnh trống; có thể chạy lại phần prompt.")
        fields["prompts"] = json.dumps(prompts, ensure_ascii=False)
        progress.publish("prompts", fields["prompts"])

        progress.update(84, "📝 Đang tạo tiêu đề, mô tả và SEO...")
        metadata = parse_object(call(
            f"Soạn YouTube tiêu đề, mô tả và 15 từ khóa SEO bằng {language}. "
            "Sát ý gốc, giàu ngữ cảnh, không bịa tình tiết, mô tả có emoji phù hợp. "
            'Chỉ trả JSON {"title":"...", "description":"...", "tags":["..."]}.\n\n'
            f"Tiêu đề gốc: {title}\nMô tả gốc: {description}\n"
            f"Nội dung:\n{brief}"
        ), "title")
        tags = metadata.get("tags", [])
        tags = (", ".join(map(str, tags)) if isinstance(tags, list) else str(tags))
        new_title = str(metadata.get("title", "")).strip()
        new_desc = str(metadata.get("description", "")).strip()
        if not all([new_title, new_desc, tags.strip()]):
            raise ValueError("Thiếu tiêu đề, mô tả hoặc từ khóa SEO trong phản hồi API.")
        fields["new_title"] = new_title
        fields["new_description"] = new_desc
        fields["seo_tags"] = tags
        fields["metadata"] = "\n\n".join([new_title, new_desc, tags])
        fields["language"] = language
        for item in ("new_title", "new_description", "seo_tags", "metadata", "language"):
            progress.publish(item, fields[item])
        result["ok"] = True
        progress.update(100, "✅ Hoàn thành. Đã lưu vào danh sách phiên.")
    except Exception as exc:
        # Redact credentials in provider error messages.
        safe_error = str(exc).replace(api_key, "[API KEY ĐÃ ẨN]")
        extra_key = snapshot.get("supadata_key", "")
        if extra_key:
            safe_error = safe_error.replace(extra_key, "[KEY PHỤ ĐỀ ĐÃ ẨN]")
        result["error"] = safe_error[:700]
        progress.update(100, "⚠️ Tác vụ kết thúc nhưng có lỗi.")
    return result

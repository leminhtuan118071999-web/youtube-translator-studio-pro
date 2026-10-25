"""Background worker for YouTube Translator Studio Pro.

Never import Streamlit or touch st.session_state from a worker thread.
Jobs and API keys exist in process memory, not persistent storage.
"""
import json
import re
import threading
from urllib.parse import urlsplit

import requests
from youtube_transcript_api import YouTubeTranscriptApi

from api_clients import generate_text


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


def fetch_subtitles(video_id):
    tracks = list(YouTubeTranscriptApi().list(video_id))
    preferred = {"vi": 0, "en": 1, "pl": 2}
    tracks.sort(key=lambda tr: (bool(tr.is_generated),
                                preferred.get(tr.language_code, 10)))
    for track in tracks:
        try:
            segments = track.fetch()
            text = " ".join(
                item.text.strip() for item in segments
                if isinstance(getattr(item, "text", None), str) and item.text.strip()
            )
            if text.strip():
                return text, track.language
        except Exception:
            continue
    raise ValueError("Video không có phụ đề truy cập được; YouTube có thể đang hạn chế.")


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
    if len(text) <= 24000:
        return text
    all_chunks = list(chunk_text(text, 15000))
    briefs = []
    for idx, chunk in enumerate(all_chunks, 1):
        progress.check_cancelled()
        briefs.append(call(
            "Summarize chronological events, character consistency and visual "
            "details without inventing anything. 180-280 words. "
            f"Part {idx}/{len(all_chunks)}:\n" + chunk
        ))
    return "\n".join(briefs)


def run_full_job(snapshot, progress):
    """Return completed/partial fields. Never return or store the API key."""
    result = {"ok": False, "fields": {}, "error": ""}
    fields = result["fields"]
    api_key = snapshot["api_key"]

    def call(prompt):
        progress.check_cancelled()
        return generate_text(
            snapshot["provider"], snapshot["base_url"],
            snapshot["model"], api_key, prompt
        )

    try:
        progress.check_cancelled()
        source = snapshot.get("source", "")
        vid = youtube_id(snapshot.get("url", ""))
        title = snapshot.get("title", "")
        description = snapshot.get("description", "")
        language = snapshot["language"]
        if vid:
            progress.update(5, "📥 Đang trích xuất phụ đề YouTube...")
            source, caption_lang = fetch_subtitles(vid)
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
        if not source.strip():
            raise ValueError("Không lấy được phụ đề. Hãy kiểm tra link video.")
        if len(source) > 350000:
            raise ValueError("Phụ đề quá dài (hơn 350.000 ký tự).")
        fields["source"] = source
        progress.publish("source", source)

        chunks = list(chunk_text(source))
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
        result["error"] = str(exc).replace(api_key, "[API KEY ĐÃ ẨN]")[:700]
        progress.update(100, "⚠️ Tác vụ kết thúc nhưng có lỗi.")
    return result

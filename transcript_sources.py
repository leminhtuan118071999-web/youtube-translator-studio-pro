"""Reliable transcript retrieval with an optional paid/free-tier API fallback.

No scraping bypass is promised. The native YouTube method often fails on
cloud IP ranges. Supadata requires a separate key and may charge credits.
"""
import re
import time

import requests
from youtube_transcript_api import YouTubeTranscriptApi

SUPADATA_ENDPOINT = "https://api.supadata.ai/v1/transcript"
MAX_TRANSCRIPT_CHARS = 350000


def native_transcript(video_id):
    tracks = list(YouTubeTranscriptApi().list(video_id))
    tracks.sort(key=lambda t: (
        bool(t.is_generated),
        {"vi": 0, "en": 1, "pl": 2}.get(t.language_code, 10),
    ))
    if not tracks:
        raise ValueError("Video không có phụ đề sẵn có.")
    for track in tracks:
        try:
            data = track.fetch()
            text = " ".join(
                x.text.strip() for x in data
                if isinstance(getattr(x, "text", None), str) and x.text.strip()
            )
            if text.strip():
                return text, track.language
        except Exception:
            continue
    raise ValueError("Không thể tải bất kỳ bản phụ đề sẵn có nào.")


def parse_supadata_result(payload):
    if not isinstance(payload, dict):
        raise ValueError("Dịch vụ phụ đề trả phản hồi không hợp lệ.")
    content = payload.get("content")
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        text = " ".join(
            str(item.get("text", "")).strip()
            for item in content if isinstance(item, dict)
        ).strip()
    else:
        raise ValueError("Dịch vụ phụ đề không trả văn bản.")
    if not text:
        raise ValueError("Không có nội dung phụ đề trong phản hồi.")
    if len(text) > MAX_TRANSCRIPT_CHARS:
        raise ValueError("Phụ đề quá dài, vượt giới hạn 350.000 ký tự.")
    return text, payload.get("lang") or "Tự động"


def _get(url, key, params=None):
    try:
        response = requests.get(
            url,
            headers={"x-api-key": key},
            params=params,
            timeout=(10, 55),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise RuntimeError("Không kết nối được dịch vụ lấy phụ đề dự phòng.") from exc
    if 300 <= response.status_code < 400:
        raise RuntimeError("Dịch vụ phụ đề chuyển hướng URL không mong đợi.")
    if not response.ok:
        try:
            data = response.json()
            if isinstance(data, dict):
                msg = data.get("message") or data.get("error") or response.reason
            else:
                msg = response.reason
        except ValueError:
            msg = response.reason
        msg = str(msg).replace(key, "[KEY ĐÃ ẨN]")[:240]
        raise RuntimeError(
            f"Dịch vụ phụ đề dự phòng lỗi HTTP {response.status_code}: {msg}. "
            "Kiểm tra key, số lượt sử dụng và quyền truy cập video."
        )
    try:
        return response.status_code, response.json()
    except ValueError as exc:
        raise RuntimeError("Dịch vụ phụ đề không trả JSON hợp lệ.") from exc


def supadata_transcript(video_id, key, progress=None, sleep=time.sleep):
    """GET /transcript; support immediate and async (202 + jobId) results."""
    token = (key or "").strip()
    if not token:
        raise ValueError("Chưa có API key dịch vụ phụ đề dự phòng.")
    url = f"https://www.youtube.com/watch?v={video_id}"
    status, data = _get(
        SUPADATA_ENDPOINT, token,
        params={"url": url, "text": "true", "mode": "auto"},
    )
    if status != 202 and isinstance(data, dict) and "content" in data:
        return parse_supadata_result(data)
    job_id = data.get("jobId") if isinstance(data, dict) else None
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{3,128}", job_id):
        raise RuntimeError("Dịch vụ phụ đề chưa có dữ liệu và không trả mã tác vụ.")
    for attempt in range(24):
        if progress:
            progress.check_cancelled()
            progress.update(7, "📥 Dịch vụ dự phòng đang xử lý phụ đề...")
        sleep(3)
        _, value = _get(SUPADATA_ENDPOINT + "/" + job_id, token)
        if isinstance(value, dict):
            if value.get("status") == "failed":
                raise RuntimeError("Dịch vụ dự phòng không thể trích xuất video này.")
            if "content" in value:
                return parse_supadata_result(value)
    raise TimeoutError(
        "Dịch vụ phụ đề chưa xử lý xong. Hãy thử lại sau hoặc tải file .srt/.vtt/.txt."
    )


def fetch_with_fallback(video_id, supadata_key="", progress=None):
    """Try native subtitles then optional Supadata; return source metadata."""
    if progress:
        progress.check_cancelled()
        progress.update(3, "📥 Thử phụ đề YouTube trực tiếp...")
    try:
        text, lang = native_transcript(video_id)
        return text, lang, "YouTube trực tiếp"
    except Exception:
        # Hide the large English upstream error; typical cause is cloud IP block.
        if not (supadata_key or "").strip():
            raise RuntimeError(
                "YouTube đang chặn lấy phụ đề trực tiếp trên máy chủ Streamlit "
                "(hoặc video không có phụ đề). Để tiếp tục, hãy nhập "
                "Supadata API key trong mục 'Phụ đề dự phòng', hoặc tải tệp "
                ".srt/.vtt/.txt trong mục 'Nhập phụ đề từ máy'."
            ) from None
    if progress:
        progress.check_cancelled()
        progress.update(6, "📥 Thử dịch vụ lấy phụ đề dự phòng...")
    text, lang = supadata_transcript(video_id, supadata_key, progress=progress)
    return text, lang, "Supadata"


def parse_uploaded_subtitles(filename, data):
    if not data or len(data) > 4 * 1024 * 1024:
        raise ValueError("File rỗng hoặc lớn hơn 4 MB.")
    if not filename.lower().endswith((".txt", ".srt", ".vtt")):
        raise ValueError("Chỉ hỗ trợ tệp .txt, .srt hoặc .vtt.")
    raw = data.decode("utf-8-sig", errors="replace")
    if filename.lower().endswith(".txt"):
        text = raw.strip()
    else:
        lines = []
        for line in raw.splitlines():
            line = line.strip()
            if (
                not line or line in {"WEBVTT", "Kind: captions"}
                or re.match(r"^\d+$", line)
                or "-->" in line
                or line.startswith(("NOTE", "Language:", "STYLE", "REGION"))
                or re.match(r"^\d\d:\d\d", line)
            ):
                continue
            line = re.sub(r"<[^>]*>", "", line)
            if line and (not lines or line != lines[-1]):
                lines.append(line)
        text = " ".join(lines).strip()
    if not text:
        raise ValueError("Không tìm thấy văn bản phụ đề trong file.")
    if len(text) > MAX_TRANSCRIPT_CHARS:
        raise ValueError("Nội dung file vượt giới hạn 350.000 ký tự.")
    return text

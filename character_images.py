"""Automatic character portraits kept separate per Streamlit session.

The provider must explicitly support image generation. The binary data are
never stored in GitHub, API settings, browser text snapshots or Supabase JSON.
A Streamlit server restart clears this process-local image cache.
"""
import base64
from io import BytesIO
import json
import re
import threading
import zipfile

import requests

IMAGE_MODEL = "gpt-image-2.5-flare"
MAX_CHARACTERS = 8
MAX_IMAGE_BYTES = 12 * 1024 * 1024


def character_specs(profile):
    """Use structured AI metadata or a conservative 'Name: description' fallback."""
    results = []
    candidate = profile.get("characters", [])
    if isinstance(candidate, list):
        for entry in candidate:
            if isinstance(entry, dict):
                name, desc = entry.get("name"), entry.get("description")
                if isinstance(name, str) and isinstance(desc, str) and name.strip() and desc.strip():
                    results.append((name.strip()[:80], desc.strip()[:1300]))
    if not results:
        bible = profile.get("character_bible", "")
        if isinstance(bible, str):
            for line in bible.splitlines():
                matched = re.match(r"^\s*[-*]?\s*([^:：]{1,70})\s*[:：]\s*(.{12,})$", line)
                if matched:
                    results.append((matched.group(1).strip(), matched.group(2).strip()[:1300]))
    seen = set()
    unique = []
    for name, desc in results:
        slug = filename_part(name).casefold()
        if slug not in seen:
            unique.append((name, desc))
            seen.add(slug)
    return unique[:MAX_CHARACTERS]


def filename_part(value):
    """Make a safe archive filename while preserving recognizable names."""
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(value))
    value = re.sub(r"\s+", "_", value).strip(" ._")[:90]
    return value or "Nhan_vat"


def create_character_png(api_key, name, description, *, style, bible, model=IMAGE_MODEL):
    """Use a real GPT Image API, never a text model to invent a PNG."""
    if not api_key or not isinstance(api_key, str):
        raise ValueError("Cần API key tạo ảnh OpenAI.")
    prompt = (
        f"Create ONE character reference portrait for {name}. "
        f"EXACT identity and costume: {description}. "
        f"Art direction: {style}. Other character continuity: {bible[:2500]}. "
        "Full-body solo character, clear face, uncluttered neutral background, "
        "consistent costume and features, no label, watermark or lettering. "
        "Do not add other characters."
    )
    response = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model, "prompt": prompt[:11000], "size": "1024x1024",
            "n": 1, "quality": "medium", "output_format": "png",
        },
        timeout=150,
    )
    if not response.ok:
        if response.status_code == 401:
            raise RuntimeError(
                "HTTP 401: OpenAI không xác thực được API key tạo ảnh. "
                "Hãy mở '🖼️ API tạo ảnh nhân vật' và nhập API key OpenAI "
                "hợp lệ từ platform.openai.com/api-keys; không dùng Groq, "
                "Gemini, OpenRouter hay token ChatGPT ở trường này. "
                "Nếu key đã đổi, xóa key cũ trong ô, nhập lại rồi "
                "nhấn Chạy lại riêng — Ảnh nhân vật."
            )
        if response.status_code == 403:
            raise RuntimeError(
                "HTTP 403: tài khoản hoặc dự án OpenAI chưa được phép sử dụng "
                "model tạo ảnh; hãy kiểm tra quyền truy cập của dự án."
            )
        if response.status_code == 429:
            raise RuntimeError(
                "HTTP 429: API ảnh đang giới hạn yêu cầu hoặc quota; "
                "kiểm tra hạn mức và billing của dự án."
            )
        raise RuntimeError(
            f"API tạo ảnh trả lỗi HTTP {response.status_code}. "
            "Kiểm tra model ảnh, tài khoản, quyền hoặc hạn mức; "
            "không tự động yêu cầu tạo lại ảnh để tránh phát sinh phí."
        )
    try:
        b64 = response.json()["data"][0]["b64_json"]
        binary = base64.b64decode(b64, validate=True)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("API tạo ảnh không trả nội dung PNG hợp lệ.") from exc
    if len(binary) > MAX_IMAGE_BYTES or not binary.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Ảnh tạo ra không phải PNG hoặc vượt giới hạn dung lượng.")
    return binary


class CharacterImageStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._sessions = {}

    def save(self, scope, sid, name, image):
        if not scope or not sid or not isinstance(image, bytes):
            raise ValueError("Dữ liệu ảnh không hợp lệ.")
        with self._lock:
            self._sessions.setdefault((scope, sid), {})[name] = image

    def images(self, scope, sid):
        with self._lock:
            return dict(self._sessions.get((scope, sid), {}))

    def clear(self, scope, sid):
        with self._lock:
            self._sessions.pop((scope, sid), None)


IMAGE_STORE = CharacterImageStore()


def session_images_zip(images, session_name):
    """Download one ZIP per session; the browser chooses the save location."""
    data = BytesIO()
    safe_session = filename_part(session_name)
    used = set()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, image in images.items():
            base = filename_part(name)
            filename = base + ".png"
            number = 2
            while filename.casefold() in used:
                filename = f"{base}_{number}.png"
                number += 1
            used.add(filename.casefold())
            archive.writestr(filename, image)
    return f"{safe_session}_nhan_vat.zip", data.getvalue()

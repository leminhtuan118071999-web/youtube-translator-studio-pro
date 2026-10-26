"""AI image editing of YouTube thumbnails via official Gemini/OpenAI endpoints.

This is an image-to-image feature. Text-only Groq/Claude providers cannot
generate images. Do not log, persist or forward an image API key to third parties
other than the selected official image provider.
"""
import base64
import hashlib
import io
import json
import re

from PIL import Image, ImageOps, UnidentifiedImageError
import requests

from api_clients import gemini_generate_endpoint

GEMINI_IMAGE_MODELS = ("gemini-2.5-flash-image", "gemini-3.1-flash-image")
OPENAI_IMAGE_MODELS = ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst")
MAX_INPUT_BYTES = 9_000_000
MAX_OUTPUT_BYTES = 14_000_000
ALLOWED_LANGUAGES = re.compile(r"^[\w\sÀ-ỹ()\-]{2,75}$", re.UNICODE)


def normalize_thumbnail(data):
    """Verify actual pixels, constrain dimensions and emit PNG image bytes."""
    if not isinstance(data, bytes) or not (0 < len(data) <= MAX_INPUT_BYTES):
        raise ValueError("Thumbnail phải là ảnh PNG/JPEG/WebP không quá 9 MB.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            if image.width < 200 or image.height < 100:
                raise ValueError("Thumbnail quá nhỏ để chỉnh sửa bằng AI.")
            if image.width * image.height > 18_000_000:
                raise ValueError("Ảnh vượt quá giới hạn độ phân giải.")
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, format="PNG", optimize=True)
            result = out.getvalue()
            if len(result) > MAX_INPUT_BYTES:
                raise ValueError("Thumbnail vượt giới hạn 9 MB sau khi chuẩn hóa.")
            return result
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Không thể đọc thumbnail. Chỉ hỗ trợ ảnh PNG/JPEG/WebP.") from exc


def _verified_output(data):
    if not isinstance(data, bytes) or not (0 < len(data) <= MAX_OUTPUT_BYTES):
        raise RuntimeError("AI trả về ảnh trống hoặc vượt giới hạn dung lượng.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            if im.width < 200 or im.height < 100 or im.width * im.height > 25_000_000:
                raise RuntimeError("Ảnh AI trả về có kích thước không hợp lệ.")
            im = ImageOps.exif_transpose(im).convert("RGB")
            im = ImageOps.fit(
                im, (1280, 720), method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5)
            )
            output = io.BytesIO()
            im.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise RuntimeError("API không trả về tệp ảnh hợp lệ.") from exc


def _fail(response, token):
    detail = "Lỗi dịch vụ chỉnh sửa ảnh."
    try:
        obj = response.json()
        info = obj.get("error") if isinstance(obj, dict) else None
        if isinstance(info, dict):
            detail = str(info.get("message") or detail)
        elif isinstance(info, str):
            detail = info
    except (ValueError, TypeError, AttributeError):
        pass
    if token:
        detail = detail.replace(token, "[API KEY ẨN]")
    detail = detail[:350]
    hint = {
        400: "Kiểm tra model chỉnh sửa ảnh và định dạng yêu cầu.",
        401: "API key không hợp lệ hoặc hết hiệu lực.",
        403: "API key chưa được cấp quyền dùng model ảnh.",
        404: "Model ảnh không tồn tại hoặc không khả dụng.",
        429: "Đã vượt hạn mức; model ảnh có thể không nằm trong gói miễn phí.",
        502: "Gateway/upstream chỉnh ảnh đang gặp sự cố.",
        503: "Dịch vụ tạo ảnh hiện không sẵn sàng.",
    }.get(response.status_code, "Kiểm tra quyền model hoặc thử lại sau.")
    raise RuntimeError(f"HTTP {response.status_code}: {detail}. {hint}")


def _request_json(url, token, payload, *, gemini, timeout=120):
    headers = (
        {"x-goog-api-key": token, "Content-Type": "application/json"}
        if gemini else
        {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    )
    try:
        response = requests.post(
            url, headers=headers, json=payload,
            timeout=(10, timeout), allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise RuntimeError("Không kết nối được máy chủ xử lý ảnh. Kiểm tra mạng/API.") from exc
    if not response.ok:
        _fail(response, token)
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("Máy chủ chỉnh ảnh không trả dữ liệu JSON hợp lệ.") from exc


def _extract_gemini_image(payload):
    for candidate in payload.get("candidates", []):
        for part in (candidate.get("content") or {}).get("parts", []):
            if part.get("thought"):
                continue
            block = part.get("inlineData") or part.get("inline_data") or {}
            if (block.get("mimeType") or block.get("mime_type") or "").startswith("image/"):
                return base64.b64decode(block["data"], validate=True)
    raise RuntimeError(
        "Gemini không trả về ảnh. Kiểm tra quyền dùng model ảnh hoặc bộ lọc nội dung."
    )


def _extract_openai_image(payload):
    rows = payload.get("data") or []
    if rows and isinstance(rows[0].get("b64_json"), str):
        return base64.b64decode(rows[0]["b64_json"], validate=True)
    raise RuntimeError("OpenAI không trả ảnh base64. Kiểm tra model và quyền Images API.")


def _text_response(data, gemini):
    if gemini:
        return "\n".join(
            str(p.get("text", ""))
            for c in data.get("candidates", [])
            for p in (c.get("content") or {}).get("parts", [])
            if isinstance(p, dict) and not p.get("thought")
        )
    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("API không trả về văn bản OCR.") from exc


def recognize_and_translate(source_png, language, provider, key):
    """Multimodal OCR + translation for faithful quoted text in edit prompt.

    If OCR sees no text, returns empty strings; does not invent text.
    """
    if not key:
        raise ValueError("Cần API key có quyền dùng model ảnh/nhận diện chữ.")
    if not isinstance(language, str) or not ALLOWED_LANGUAGES.fullmatch(language):
        raise ValueError("Ngôn ngữ đích không hợp lệ.")
    task = (
        "Read ONLY text visibly printed in this YouTube thumbnail. Translate "
        f"the visible text faithfully to {language}. Return ONLY JSON with "
        'two strings: {"original_text": "...", "translated_text": "..."} . '
        "Preserve proper names and intended meaning. Keep the translation "
        "short, punchy, natural for a YouTube thumbnail. If absolutely no "
        "visible text exists, return empty strings. No invented text."
    )
    encoded = base64.b64encode(source_png).decode("ascii")
    if provider == "Gemini":
        response = _request_json(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-3.5-flash-lite:generateContent",
            key,
            {"contents": [{"parts": [
                {"inlineData": {"mimeType": "image/png", "data": encoded}},
                {"text": task}
            ]}], "generationConfig": {"responseMimeType": "application/json"}},
            gemini=True, timeout=70,
        )
        text = _text_response(response, True)
    elif provider == "OpenAI":
        response = _request_json(
            "https://api.openai.com/v1/chat/completions",
            key,
            {"model": "gpt-4.1-mini", "max_tokens": 500,
             "response_format": {"type": "json_object"},
             "messages": [{"role": "user", "content": [
                 {"type": "text", "text": task},
                 {"type": "image_url", "image_url": {
                     "url": "data:image/png;base64," + encoded,
                     "detail": "high"
                 }}
             ]}]}, gemini=False, timeout=70,
        )
        text = _text_response(response, False)
    else:
        raise ValueError("Dịch vụ ảnh phải là Gemini hoặc OpenAI.")
    try:
        parsed = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
        original = str(parsed.get("original_text") or "").strip()[:900]
        translated = str(parsed.get("translated_text") or "").strip()[:900]
        if bool(original) != bool(translated):
            raise ValueError()
        return original, translated
    except (ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError("AI không trả đúng văn bản OCR/dịch dạng JSON. Hãy thử lại.") from exc


def build_edit_prompt(mode, language, *, original_text="", translated_text="",
                      preserve_layout=True, clean_text=True):
    instructions = (
        "You are editing the PROVIDED original YouTube thumbnail image, not "
        "inventing a new story. Create ONE professional high-quality 16:9 "
        "YouTube thumbnail (1280x720). Preserve the original identity, "
        "real people, faces, pose, clothing, setting, props, color palette, "
        "camera framing, lighting and distinctive artistic treatment. "
        "Avoid hallucinated faces, extra fingers or objects. "
    )
    if preserve_layout:
        instructions += (
            "Keep the original subject placement, perspective and composition "
            "as faithfully as the image model allows. "
        )
    if mode == "recreate":
        return instructions + (
            "Carefully RECREATE/RESTORE the original thumbnail with cleaner "
            "edges, sharper legibility, more balanced graphic design and "
            "professional contrast. Preserve any original visible text exactly, "
            "without adding slogans or changing its language. "
            "Improve text alignment and spacing only if necessary."
        )
    if mode != "translate":
        raise ValueError("Chế độ thumbnail không hợp lệ.")
    if not isinstance(language, str) or not ALLOWED_LANGUAGES.fullmatch(language):
        raise ValueError("Ngôn ngữ đích không hợp lệ.")
    instructions += (
        f"Replace visible overlay text with accurately translated {language} "
        "text. Avoid automatically translating brand names, watermarks, "
        "channel logos or intentionally untranslatable proper nouns. "
    )
    if clean_text:
        instructions += (
            "First remove ALL original overlaid headline/caption lettering "
            "completely. Reconstruct the occluded scene with seamless image "
            "inpainting and natural textures, without blurry patches, ghost "
            "letters, residual glyphs or opaque rectangles. "
        )
    if original_text and translated_text:
        instructions += (
            "The original thumbnail lettering was: "
            + json.dumps(original_text, ensure_ascii=False)
            + ". Replace this text with EXACTLY "
            + json.dumps(translated_text, ensure_ascii=False)
            + ". Do not paraphrase or add any other words. "
        )
    else:
        instructions += (
            "Read the thumbnail text visually and translate only words you "
            "can clearly see. If no text is present, do not introduce new text. "
        )
    return instructions + (
        "Set the translated typography bold, readable at mobile size, "
        "well kerned, professionally line-broken and neatly aligned to "
        "the original text's location. Use similar original font style, "
        "outlines, accents, shadow and hierarchy where helpful. "
        "Do not cover faces or key objects; prioritize legibility."
    )


def edit_thumbnail(source_png, prompt, provider, key, model):
    if not key or len(key.strip()) < 8:
        raise ValueError("Nhập API key Gemini/OpenAI hợp lệ để tạo ảnh.")
    if not isinstance(prompt, str) or len(prompt) > 12_000:
        raise ValueError("Nội dung chỉnh sửa ảnh không hợp lệ.")
    if provider == "Gemini":
        if model not in GEMINI_IMAGE_MODELS:
            raise ValueError("Model Gemini chỉnh ảnh không hợp lệ.")
        url = gemini_generate_endpoint(
            "https://generativelanguage.googleapis.com/v1beta", model
        )
        payload = {
            "contents": [{"parts": [
                {"text": prompt},
                {"inlineData": {
                    "mimeType": "image/png",
                    "data": base64.b64encode(source_png).decode("ascii"),
                }},
            ]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "responseFormat": {"image": {"aspectRatio": "16:9"}}
            }
        }
        response = _request_json(url, key, payload, gemini=True, timeout=180)
        image_data = _extract_gemini_image(response)
    elif provider == "OpenAI":
        if model not in OPENAI_IMAGE_MODELS:
            raise ValueError("Model OpenAI chỉnh ảnh không hợp lệ.")
        try:
            response = requests.post(
                "https://api.openai.com/v1/images/edits",
                headers={"Authorization": "Bearer " + key},
                data={"model": model, "prompt": prompt, "size": "1536x864",
                      "quality": "medium"},
                files={"image": ("thumbnail.png", source_png, "image/png")},
                timeout=(10, 240), allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise RuntimeError("Không kết nối được OpenAI Images API.") from exc
        if not response.ok:
            _fail(response, key)
        try:
            image_data = _extract_openai_image(response.json())
        except ValueError as exc:
            raise RuntimeError("OpenAI không trả về ảnh hợp lệ.") from exc
    else:
        raise ValueError("Dịch vụ ảnh phải là Gemini hoặc OpenAI.")
    try:
        return _verified_output(image_data)
    except (ValueError, base64.binascii.Error) as exc:
        raise RuntimeError("Phản hồi tạo ảnh bị lỗi mã hóa.") from exc

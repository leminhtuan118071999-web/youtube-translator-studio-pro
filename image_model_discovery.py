"""Discover supported image-editing models from official provider APIs.

GET /models lists model IDs but does NOT guarantee account-level edit permission.
A live edit is only attempted after the user presses a generate button.
Never log or store raw API keys in discovery results.
"""
import hashlib
import re

import requests

GEMINI_EDIT_MODELS = (
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
    "gemini-3-pro-image",
    "gemini-2.5-flash-image",
)
OPENAI_EDIT_MODELS = (
    "gpt-image-2.5-sunburst",
    "gpt-image-2.5-flare",
    "gpt-image-2",
    "gpt-image-1.5",
    "gpt-image-1-mini",
)
# Snapshot variants share the same editing API; restrict to a safe model ID.
MODEL_ID_RE = re.compile(r"^[A-Za-z][a-zA-Z0-9._-]{1,110}$")
OPENAI_SNAPSHOT_RE = re.compile(r"^gpt-image-(?:2\.5-(?:sunburst|flare)|2)-20\d{2}-\d{2}-\d{2}$")


def supported_image_model(provider, model):
    """True only for documented models supported by our image-edit endpoints."""
    if not isinstance(model, str) or not MODEL_ID_RE.fullmatch(model):
        return False
    if provider == "Gemini":
        return model in GEMINI_EDIT_MODELS
    if provider == "OpenAI":
        return model in OPENAI_EDIT_MODELS or bool(OPENAI_SNAPSHOT_RE.fullmatch(model))
    return False


def rank_image_models(provider, available):
    """Preserve provider-confirmed models only, preferred model first."""
    preferred = GEMINI_EDIT_MODELS if provider == "Gemini" else OPENAI_EDIT_MODELS
    if provider not in ("Gemini", "OpenAI"):
        raise ValueError("Nhà cung cấp ảnh không hỗ trợ.")
    cleaned = {
        model[7:] if provider == "Gemini" and model.startswith("models/") else model
        for model in available
        if isinstance(model, str)
    }
    usable = {m for m in cleaned if supported_image_model(provider, m)}
    extras = sorted(usable - set(preferred))
    return [m for m in preferred if m in usable] + extras


def key_fingerprint(provider, token):
    """Nonreversible marker so reruns never scan the same provider/key repeatedly."""
    if provider not in ("Gemini", "OpenAI"):
        raise ValueError("Nhà cung cấp ảnh không hỗ trợ.")
    token = token.strip() if isinstance(token, str) else ""
    return hashlib.sha256((provider + "\0" + token).encode("utf-8")).hexdigest()


def discover_image_models(provider, token):
    """One GET to official /models, no edit/generation charges initiated here.

    Does not infer image support from Gemini 'generateContent' alone because
    text-only models also expose that method. A strict, maintained allowlist
    of documented image edit IDs avoids false positive selections.
    """
    if provider not in ("Gemini", "OpenAI"):
        raise ValueError("Chỉ hỗ trợ quét model ảnh Gemini và OpenAI.")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Bạn cần nhập API key trước khi quét model.")
    if provider == "Gemini":
        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
        headers = {"x-goog-api-key": token.strip()}
    else:
        url = "https://api.openai.com/v1/models"
        headers = {"Authorization": "Bearer " + token.strip()}
    try:
        response = requests.get(
            url, headers=headers, timeout=(7, 15), allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise RuntimeError("Không kết nối được API liệt kê model. Hãy kiểm tra mạng.") from exc
    if not response.ok:
        # Never reflect a provider error message; some gateways echo token.
        explanations = {
            401: "API key không hợp lệ hoặc đã hết hiệu lực.",
            403: "API key chưa có quyền xem danh sách model.",
            404: "Nhà cung cấp không hỗ trợ đường dẫn liệt kê model.",
            429: "Đã vượt giới hạn quét model; hãy thử lại sau.",
            502: "Máy chủ API tạm thời gặp lỗi.",
        }
        raise RuntimeError(
            f"Không quét được model (HTTP {response.status_code}). "
            + explanations.get(response.status_code, "Thử lại sau hoặc chọn model thủ công.")
        )
    try:
        body = response.json()
    except (ValueError, TypeError) as exc:
        raise RuntimeError("API trả về danh sách model không phải JSON.") from exc
    if not isinstance(body, dict):
        raise RuntimeError("API không trả danh sách model hợp lệ.")
    items = body.get("models") if provider == "Gemini" else body.get("data")
    if not isinstance(items, list):
        raise RuntimeError("API không trả danh sách model trong trường models/data.")
    ids = []
    for item in items[:1500]:
        if not isinstance(item, dict):
            continue
        if provider == "Gemini":
            methods = item.get("supportedGenerationMethods", [])
            if isinstance(methods, list) and methods and "generateContent" not in methods:
                continue
            value = item.get("name") or item.get("baseModelId")
        else:
            value = item.get("id")
        if isinstance(value, str):
            ids.append(value)
    return rank_image_models(provider, ids)

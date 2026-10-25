"""Multi-provider API client for text generation and model discovery.

Never persist API keys. User-controlled Base URLs are validated to prevent
requests to localhost, private networks and cloud metadata addresses.
"""
import ipaddress
import socket
from urllib.parse import urlsplit

import requests


PROVIDERS = {
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
        "secret": "GROQ_API_KEY",
        "kind": "chat",
    },
    "Google Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.8-flash",
        "secret": "GEMINI_API_KEY",
        "kind": "chat",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "secret": "OPENAI_API_KEY",
        "kind": "chat",
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-oss-120b",
        "secret": "OPENROUTER_API_KEY",
        "kind": "chat",
    },
    "DeepSeek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "secret": "DEEPSEEK_API_KEY",
        "kind": "chat",
    },
    "Together AI": {
        "base_url": "https://api.together.xyz/v1",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "secret": "TOGETHER_API_KEY",
        "kind": "chat",
    },
    "Anthropic Claude": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-5",
        "secret": "ANTHROPIC_API_KEY",
        "kind": "anthropic",
    },
    "API tương thích OpenAI (tùy chỉnh)": {
        "base_url": "",
        "model": "",
        "secret": "",
        "kind": "chat",
    },
}


def validate_base_url(raw):
    """Accept HTTPS public services only, not internal/private services."""
    raw = (raw or "").strip()
    if not raw or len(raw) > 400:
        raise ValueError("Bạn cần nhập Base URL hợp lệ (https://...).")
    url = urlsplit(raw)
    if (
        url.scheme.lower() != "https"
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or url.port not in (None, 443)
    ):
        raise ValueError("Base URL phải là HTTPS công khai, không chứa user/password, query hay port lạ.")
    hostname = url.hostname.lower().rstrip(".")
    if (
        hostname in {"localhost", "metadata.google.internal", "metadata"}
        or hostname.endswith((".localhost", ".local", ".internal", ".test"))
        or "." not in hostname
    ):
        raise ValueError("Không cho phép Base URL trỏ tới địa chỉ nội bộ.")
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        addr = None
    if addr is not None and not addr.is_global:
        raise ValueError("Không cho phép IP riêng, nội bộ hoặc đặc biệt.")
    # Reject custom hostnames resolving to internal IPs.
    try:
        destinations = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Không phân giải được tên miền Base URL.") from exc
    if not destinations:
        raise ValueError("Tên miền Base URL không có địa chỉ IP.")
    for item in destinations:
        ip = ipaddress.ip_address(item[4][0].split("%")[0])
        if not ip.is_global:
            raise ValueError("Base URL trỏ tới IP không công khai.")
    return raw.rstrip("/")


def api_endpoint(base_url, kind, resource):
    base = validate_base_url(base_url)
    path = urlsplit(base).path.rstrip("/").lower()
    if path.endswith(("/chat/completions", "/messages", "/models", "/responses")):
        raise ValueError("Base URL chỉ đến thư mục API (ví dụ /v1), không thêm /chat/completions.")
    if kind == "anthropic":
        return base + ("/messages" if resource == "chat" else "/models")
    return base + ("/chat/completions" if resource == "chat" else "/models")


def api_headers(kind, token):
    if kind == "anthropic":
        return {
            "x-api-key": token,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
    return {"Authorization": "Bearer " + token, "Content-Type": "application/json"}


def _request(method, url, headers, **kwargs):
    # Disable environment proxies; never follow redirects carrying credentials.
    with requests.Session() as session:
        session.trust_env = False
        resp = session.request(
            method, url, headers=headers, allow_redirects=False,
            timeout=(10, 150), **kwargs
        )
    if 300 <= resp.status_code < 400:
        raise RuntimeError("API trả về chuyển hướng. Hãy dùng đúng Base URL, không theo redirect vì bảo mật.")
    return resp


def _error(response, token):
    try:
        payload = response.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        reason = error.get("message") if isinstance(error, dict) else str(error)
        reason = reason or response.text[:350]
    except (ValueError, TypeError):
        reason = response.text[:350]
    detail = str(reason).replace(token, "[API KEY ĐÃ ẨN]")[:550]
    hint = {
        400: "Kiểm tra Model và định dạng API.",
        401: "API key không hợp lệ.",
        403: "Tài khoản hoặc model chưa có quyền.",
        404: "Kiểm tra Base URL và Model.",
        429: "Quá giới hạn tốc độ hoặc quota.",
    }.get(response.status_code, "Kiểm tra cấu hình và thử lại.")
    return RuntimeError(f"HTTP {response.status_code}: {detail}. {hint}")


def generate_text(provider, base_url, model, api_key, prompt):
    if provider not in PROVIDERS:
        raise ValueError("Nhà cung cấp API không hợp lệ.")
    token = (api_key or "").strip()
    if not token:
        raise ValueError("Chưa nhập API key.")
    model = (model or "").strip()
    if not model or len(model) > 180 or any(ch.isspace() for ch in model):
        raise ValueError("Hãy nhập Model ID chính xác (không chứa khoảng trắng).")
    kind = PROVIDERS[provider]["kind"]
    endpoint = api_endpoint(base_url, kind, "chat")
    if kind == "anthropic":
        body = {
            "model": model, "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
        }
    else:
        body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    try:
        response = _request("POST", endpoint, api_headers(kind, token), json=body)
    except requests.RequestException as exc:
        raise RuntimeError("Không kết nối được nhà cung cấp AI. Hãy kiểm tra Base URL và mạng.") from exc
    if not response.ok:
        raise _error(response, token)
    try:
        obj = response.json()
        if kind == "anthropic":
            chunks = [
                item.get("text", "") for item in obj.get("content", [])
                if item.get("type") == "text"
            ]
        else:
            message = obj["choices"][0]["message"]
            content = message.get("content")
            if isinstance(content, str):
                chunks = [content]
            elif isinstance(content, list):
                chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
            else:
                chunks = []
        answer = "\n".join(str(piece) for piece in chunks if piece).strip()
        if not answer:
            raise ValueError("Không có nội dung văn bản.")
        return answer
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise RuntimeError("API có phản hồi nhưng không trả nội dung văn bản. Kiểm tra model.") from exc


def list_models(provider, base_url, api_key):
    if provider not in PROVIDERS:
        raise ValueError("Nhà cung cấp API không hợp lệ.")
    token = (api_key or "").strip()
    if not token:
        raise ValueError("Hãy nhập API key trước khi quét Model.")
    kind = PROVIDERS[provider]["kind"]
    url = api_endpoint(base_url, kind, "models")
    try:
        response = _request("GET", url, api_headers(kind, token))
    except requests.RequestException as exc:
        raise RuntimeError("Không lấy được danh sách Model. Kiểm tra mạng và Base URL.") from exc
    if not response.ok:
        raise _error(response, token)
    try:
        obj = response.json()
        items = obj.get("data", obj.get("models", []))
        models = []
        for item in items:
            if isinstance(item, dict):
                value = item.get("id") or item.get("name")
                if isinstance(value, str) and value.strip():
                    models.append(value.strip())
        return sorted(set(models), key=str.casefold)[:300]
    except (ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError("Không đọc được danh sách Model do API trả về.") from exc

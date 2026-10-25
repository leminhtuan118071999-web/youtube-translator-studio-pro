"""Multi-provider API client for text generation and model discovery.

Never persist API keys. User-controlled Base URLs are validated to prevent
requests to localhost, private networks and cloud metadata addresses.
"""
import ipaddress
import re
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



class RateLimitError(RuntimeError):
    """429 from provider; safe retry delay excludes credentials."""

    def __init__(self, message, retry_after=None, can_retry=True):
        super().__init__(message)
        self.retry_after = retry_after
        self.can_retry = can_retry


def _retry_seconds(response, message):
    """Respect Retry-After header, then provider's stated 'try again' delay."""
    try:
        value = float(response.headers.get("retry-after", ""))
        if 0 <= value <= 3600:
            return value
    except (ValueError, TypeError, AttributeError):
        pass
    match = re.search(
        r"(?:try again in|retry after|thử lại sau)\s*(\d+(?:\.\d+)?)\s*s(?:ec(?:onds?)?)?",
        str(message), flags=re.IGNORECASE
    )
    if match:
        return min(3600.0, float(match.group(1)))
    return 30.0


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
    message = f"HTTP {response.status_code}: {detail}. {hint}"
    if response.status_code == 429:
        # Daily limits cannot be fixed by a short wait.
        daily = bool(re.search(
            r"(?:requests|tokens) per day|\bRPD\b|\bTPD\b|daily quota",
            detail, re.IGNORECASE
        ))
        return RateLimitError(
            message, retry_after=_retry_seconds(response, detail),
            can_retry=not daily,
        )
    return RuntimeError(message)


def _extract_text_parts(parts):
    """Read visible answer text, never provider reasoning or tool-call payloads."""
    if isinstance(parts, str):
        return parts.strip()
    if not isinstance(parts, list):
        return ""
    chunks = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        kind = part.get("type", "text")
        if kind not in ("text", "output_text"):
            continue
        value = part.get("text", "")
        if isinstance(value, str) and value.strip():
            chunks.append(value.strip())
    return "\n".join(chunks)


def _read_provider_answer(payload, kind, provider, model):
    """Parse text from documented response shapes; explain non-text completions."""
    if not isinstance(payload, dict):
        raise RuntimeError("API trả phản hồi không phải JSON object.")
    finish_reason = "không rõ"
    if kind == "anthropic":
        answer = _extract_text_parts(payload.get("content", []))
        finish_reason = str(payload.get("stop_reason") or "không rõ")
    else:
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0] if isinstance(choices[0], dict) else {}
            message = choice.get("message") or {}
            if not isinstance(message, dict):
                message = {}
            answer = _extract_text_parts(message.get("content"))
            finish_reason = str(choice.get("finish_reason") or "không rõ")
            if not answer and message.get("tool_calls"):
                finish_reason = "tool_calls"
        else:
            # Some OpenAI-compatible proxy servers return Responses-style bodies.
            output = payload.get("output", [])
            answer = "\n".join(
                _extract_text_parts(item.get("content", []))
                for item in output if isinstance(item, dict)
                and item.get("type") == "message"
            ).strip() if isinstance(output, list) else ""
            # Gemini-compatible / v1beta-style fallback.
            if not answer and isinstance(payload.get("candidates"), list):
                candidate = payload["candidates"][0] if payload["candidates"] else {}
                candidate = candidate if isinstance(candidate, dict) else {}
                content = candidate.get("content") or {}
                parts = content.get("parts", []) if isinstance(content, dict) else []
                answer = _extract_text_parts(parts)
                finish_reason = str(candidate.get("finishReason") or "không rõ")
            if not answer and isinstance(payload.get("output_text"), str):
                answer = payload["output_text"].strip()
    if answer:
        return answer

    usage = payload.get("usage", {})
    completion = usage.get("completion_tokens") if isinstance(usage, dict) else None
    used = f", completion_tokens={completion}" if isinstance(completion, int) else ""
    desc = f"{provider} / {model}, finish_reason={finish_reason}{used}"
    if finish_reason in ("length", "max_tokens"):
        raise RuntimeError(
            f"API đã hết giới hạn token đầu ra trước khi sinh bản dịch ({desc}). "
            "Hãy tăng max completion tokens hoặc chọn model ít reasoning hơn."
        )
    if finish_reason == "tool_calls":
        raise RuntimeError(
            f"Model chỉ gửi lệnh gọi công cụ, không có văn bản để dịch ({desc}). "
            "Hãy chọn model chat tạo nội dung văn bản."
        )
    if finish_reason in ("content_filter", "safety", "SAFETY"):
        raise RuntimeError(
            f"Nhà cung cấp chặn nội dung đầu ra ({desc}). "
            "Hãy kiểm tra nội dung và chính sách của model."
        )
    raise RuntimeError(
        f"API trả về thành công nhưng không có nội dung văn bản ({desc}). "
        "Có thể model chỉ tạo phần reasoning mà chưa tạo câu trả lời cuối; "
        "hãy thử model chat khác hoặc giảm mức reasoning."
    )


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
        # Groq GPT-OSS uses reasoning tokens. Reserve enough output tokens for
        # the final translation, not just internal reasoning. These options
        # are documented for GPT-OSS; don't send them to other providers/models.
        if provider == "Groq" and model in (
            "openai/gpt-oss-20b", "openai/gpt-oss-120b"
        ):
            body["reasoning_effort"] = "low"
            # Smaller reserved completions lower TPM cost and reduce 429s.
            # Scenes need a larger budget; small translation chunks need less.
            if "ĐÚNG 20 prompt" in prompt or "CHÍNH XÁC 20" in prompt:
                body["max_completion_tokens"] = 3600
            elif "Soạn YouTube tiêu đề" in prompt or "Viết nội dung YouTube" in prompt:
                body["max_completion_tokens"] = 2200
            elif "Summarize" in prompt:
                body["max_completion_tokens"] = 1400
            else:
                body["max_completion_tokens"] = 2200
            body["include_reasoning"] = False
    try:
        response = _request("POST", endpoint, api_headers(kind, token), json=body)
    except requests.RequestException as exc:
        raise RuntimeError("Không kết nối được nhà cung cấp AI. Hãy kiểm tra Base URL và mạng.") from exc
    if not response.ok:
        raise _error(response, token)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("API trả HTTP 200 nhưng không phải JSON hợp lệ.") from exc
    return _read_provider_answer(payload, kind, provider, model)


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

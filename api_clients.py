"""Multi-provider API client for text generation and model discovery.

Never persist API keys. User-controlled Base URLs are validated to prevent
requests to localhost, private networks and cloud metadata addresses.
"""
import ipaddress
import re
import socket
from urllib.parse import urlsplit

import requests

from groq_pacing import groq_request_gate


PROVIDERS = {
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-20b",
        "secret": "GROQ_API_KEY",
        "kind": "chat",
    },
    "Google Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-3.5-flash-lite",
        "secret": "GEMINI_API_KEY",
        "kind": "gemini",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "secret": "OPENAI_API_KEY",
        "kind": "chat",
    },
    "Claude (Anthropic)": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-6",
        "secret": "ANTHROPIC_API_KEY",
        "kind": "anthropic",
    },
    "Claude Gateway (AUTH_TOKEN)": {
        "base_url": "",
        "model": "claude-sonnet-4-6",
        "secret": "",
        "kind": "anthropic",
        "auth": "bearer",
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

    "API bên thứ ba (tùy chỉnh)": {
        "base_url": "",
        "model": "",
        "secret": "",
        "kind": "chat",
        "auth": "bearer",
    },
    "API tương thích OpenAI (tùy chỉnh)": {
        "base_url": "",
        "model": "",
        "secret": "",
        "kind": "chat",
    },
}


def migrate_free_provider_settings(state):
    """Upgrade only known legacy Gemini defaults; preserve custom API setups.

    Groq's previously selected model is intentionally left untouched to avoid
    replacing a user-selected model. The Free profile control is explicit.
    """
    old_gemini = "https://generativelanguage.googleapis.com/v1beta/openai"
    old_model = "gemini-3.8-flash"
    key = "api_base_Google Gemini"
    if state.get(key, "").rstrip("/") == old_gemini:
        state[key] = PROVIDERS["Google Gemini"]["base_url"]
        model_key = "api_model_id_Google Gemini"
        if state.get(model_key) == old_model:
            state[model_key] = PROVIDERS["Google Gemini"]["model"]


def gemini_generate_endpoint(base_url, model):
    """Build a native Gemini URL without exposing a user-supplied path.

    The model ID must be a single safe path segment (or models/<id>).
    """
    raw = (model or "").strip()
    if raw.startswith("models/"):
        raw = raw[7:]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}", raw):
        raise ValueError("Gemini Model ID không hợp lệ; dùng tên từ 'Quét Model'.")
    url = validate_base_url(base_url)
    if url.lower().endswith("/openai"):
        # Old OpenAI-compatible base URL is not a native Gemini endpoint.
        url = url[:-7]
    return url + "/models/" + raw + ":generateContent"


def migrate_claude_settings(state):
    """Retain existing Claude credentials/models after making its name visible.

    Runs before Streamlit instantiates API widgets. Never logs or copies a
    credential outside the in-memory session mapping.
    """
    old_provider = "Anthropic Claude"
    new_provider = "Claude (Anthropic)"
    if state.get("api_provider") == old_provider:
        state["api_provider"] = new_provider
    for prefix in (
        "api_key_", "api_base_", "api_model_id_", "models_found_",
        "pending_model_", "model_picker_",
    ):
        old_name = prefix + old_provider
        new_name = prefix + new_provider
        if old_name in state:
            if new_name not in state:
                value = state[old_name]
                if prefix == "api_model_id_" and value == "claude-sonnet-4-5":
                    value = "claude-sonnet-4-6"
                state[new_name] = value
            state.pop(old_name, None)


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


def resolve_provider_config(provider, api_format=None, auth_mode=None):
    """Choose protocol and auth per request, without shared mutable state.

    Only the explicitly selected third-party provider accepts these overrides.
    """
    if provider not in PROVIDERS:
        raise ValueError("Nhà cung cấp API không hợp lệ.")
    preset = PROVIDERS[provider]
    if provider != "API bên thứ ba (tùy chỉnh)":
        return preset["kind"], preset.get("auth", "api_key" if preset["kind"] == "anthropic" else "bearer")
    kind = api_format or "chat"
    method = auth_mode or "bearer"
    if kind not in ("chat", "anthropic"):
        raise ValueError("Chuẩn API bên thứ ba không hợp lệ.")
    if method not in ("bearer", "api_key"):
        raise ValueError("Kiểu xác thực API bên thứ ba không hợp lệ.")
    return kind, method


def provider_base_url(provider, base_url, kind=None):
    """Claude Code-style gateways configure an API origin without /v1.

    Convert the origin to the equivalent native Anthropic Messages API path.
    If a gateway specifies an explicit API path, use that path unchanged.
    """
    if (
        provider == "Claude Gateway (AUTH_TOKEN)"
        or (provider == "API bên thứ ba (tùy chỉnh)" and kind == "anthropic")
    ):
        raw = (base_url or "").strip().rstrip("/")
        # A plain HTTPS origin must use /v1/messages for Anthropic Messages.
        if not urlsplit(raw).path.strip("/"):
            return raw + "/v1"
    return base_url


def api_headers(kind, token, auth_mode="api_key"):
    if kind == "gemini":
        return {"x-goog-api-key": token, "Content-Type": "application/json"}
    if kind == "anthropic":
        headers = {
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        if auth_mode == "bearer":
            headers["Authorization"] = "Bearer " + token
        else:
            headers["x-api-key"] = token
        return headers
    if auth_mode == "api_key":
        return {"x-api-key": token, "Content-Type": "application/json"}
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



class TransientProviderError(RuntimeError):
    """A provider/gateway responded with a retryable 502/503/504.

    This means the server is temporarily unavailable; it does not prove the
    key, the model or the request are invalid. A retried POST may be charged
    again if an upstream completed the first request before the gateway failed.
    """

    def __init__(self, message, status_code, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


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


def _error(response, token, provider=None):
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
        502: "Gateway/upstream tạm thời không phản hồi. Đây không nhất thiết là lỗi API key hoặc model; hãy thử lại sau.",
        503: "Dịch vụ AI phía sau gateway hiện không khả dụng; hãy thử lại sau.",
        504: "Gateway chờ upstream quá lâu và bị timeout; hãy thử lại sau.",
    }.get(response.status_code, "Kiểm tra cấu hình và thử lại.")
    if provider == "Google Gemini" and response.status_code in (400, 403, 404):
        hint += (
            " Nếu dùng API key Google AI Studio, hãy chọn đúng Model ID "
            "trong Google AI Studio và kiểm tra quyền API/quốc gia của dự án."
        )
    message = f"HTTP {response.status_code}: {detail}. {hint}"
    if response.status_code in (502, 503, 504):
        # Respect a numerical Retry-After if provided; otherwise let the
        # caller select a bounded backoff. Never retry 400/401/403/404.
        retry_after = None
        try:
            delay = float(response.headers.get("retry-after", ""))
            if 0 <= delay <= 180:
                retry_after = delay
        except (ValueError, TypeError, AttributeError):
            pass
        return TransientProviderError(
            message, status_code=response.status_code,
            retry_after=retry_after,
        )
    if response.status_code == 429:
        # Daily limits cannot be fixed by a short wait.
        daily = bool(re.search(
            r"(?:requests|tokens) per day|daily quota|per[_ -]?day|\bRPD\b|\bTPD\b",
            detail, re.IGNORECASE,
        ))
        # Gemini free-tier errors frequently say "limit: 0" for a model that
        # cannot be called in this project. No amount of retrying repairs it.
        exhausted_free = (
            provider == "Google Gemini"
            and bool(re.search(
                r"(?:limit|quota)[^\d]{0,24}0(?:\b|,)|free[_ -]?tier.*(?:limit|quota):?\s*0\b",
                detail, re.IGNORECASE,
            ))
        )
        if exhausted_free:
            message += (
                " Gemini báo hạn mức bằng 0 hoặc chưa được cấp quota cho model. "
                "Đổi sang model Flash-Lite mà tài khoản hỗ trợ, xem Usage/Limits "
                "trong Google AI Studio; chờ vài giây sẽ không khắc phục được."
            )
        return RateLimitError(
            message, retry_after=_retry_seconds(response, detail),
            can_retry=not (daily or exhausted_free),
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
        if kind not in ("text", "output_text") or part.get("thought") is True:
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
    if kind == "gemini":
        feedback = payload.get("promptFeedback") or {}
        if isinstance(feedback, dict) and feedback.get("blockReason"):
            raise RuntimeError(
                f"Gemini từ chối nội dung: {feedback.get('blockReason')}. "
                "Kiểm tra chính sách an toàn và nội dung yêu cầu."
            )

    usage = payload.get("usage", {})
    completion = usage.get("completion_tokens") if isinstance(usage, dict) else None
    used = f", completion_tokens={completion}" if isinstance(completion, int) else ""
    desc = f"{provider} / {model}, finish_reason={finish_reason}{used}"
    if finish_reason.lower() in ("length", "max_tokens", "max_output_tokens"):
        raise RuntimeError(
            f"API đã hết giới hạn token đầu ra trước khi sinh bản dịch ({desc}). "
            "Hãy tăng max completion tokens hoặc chọn model ít reasoning hơn."
        )
    if finish_reason == "tool_calls":
        raise RuntimeError(
            f"Model chỉ gửi lệnh gọi công cụ, không có văn bản để dịch ({desc}). "
            "Hãy chọn model chat tạo nội dung văn bản."
        )
    if finish_reason.lower() in ("content_filter", "safety", "blocklist", "prohibited_content"):
        raise RuntimeError(
            f"Nhà cung cấp chặn nội dung đầu ra ({desc}). "
            "Hãy kiểm tra nội dung và chính sách của model."
        )
    raise RuntimeError(
        f"API trả về thành công nhưng không có nội dung văn bản ({desc}). "
        "Có thể model chỉ tạo phần reasoning mà chưa tạo câu trả lời cuối; "
        "hãy thử model chat khác hoặc giảm mức reasoning."
    )


def generate_text(
    provider, base_url, model, api_key, prompt, *,
    api_format=None, auth_mode=None,
):
    kind, selected_auth = resolve_provider_config(provider, api_format, auth_mode)
    token = (api_key or "").strip()
    if not token:
        raise ValueError("Chưa nhập API key.")
    model = (model or "").strip()
    if not model or len(model) > 180 or any(ch.isspace() for ch in model):
        raise ValueError("Hãy nhập Model ID chính xác (không chứa khoảng trắng).")
    if kind == "gemini":
        endpoint = gemini_generate_endpoint(base_url, model)
    else:
        endpoint = api_endpoint(provider_base_url(provider, base_url, kind), kind, "chat")
    if kind == "gemini":
        # Native Google API avoids OpenAI compatibility limitations.
        # Keep test requests tiny and translation/prompt budgets bounded.
        if len(prompt) <= 80:
            output_tokens = 128
        elif "ĐÚNG 20 prompt" in prompt:
            output_tokens = 5200
        elif "Summarize" in prompt or "Condense" in prompt:
            output_tokens = 1100
        elif "Soạn YouTube tiêu đề" in prompt:
            output_tokens = 1800
        else:
            output_tokens = 3200
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": output_tokens},
        }
    elif kind == "anthropic":
        # Claude/Gateway traffic should request only the output budget each
        # operation needs. A simple connectivity check must not reserve 8192
        # tokens on an upstream proxy for a two-letter response.
        if len(prompt) <= 80:
            max_tokens = 128
        elif "ĐÚNG 20 prompt" in prompt:
            max_tokens = 5000
        elif "Summarize" in prompt or "Condense" in prompt:
            max_tokens = 1100
        elif "CHỈ xuất bản dịch" in prompt:
            max_tokens = 3600
        else:
            max_tokens = 3000
        body = {
            "model": model, "max_tokens": max_tokens,
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
    # A process-wide, per-key/model 8K TPM soft cap prevents overlapping
    # Streamlit background sessions from flooding Groq in the same minute.
    if provider == "Groq":
        groq_request_gate.acquire(token, model, prompt)
    try:
        response = _request("POST", endpoint, api_headers(kind, token, selected_auth), json=body)
    except requests.RequestException as exc:
        raise RuntimeError("Không kết nối được nhà cung cấp AI. Hãy kiểm tra Base URL và mạng.") from exc
    if not response.ok:
        failure = _error(response, token, provider)
        if provider == "Groq" and isinstance(failure, RateLimitError):
            if failure.can_retry:
                groq_request_gate.cooldown(
                    token, model, (failure.retry_after or 30.0) + 3.0
                )
        raise failure
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("API trả HTTP 200 nhưng không phải JSON hợp lệ.") from exc
    return _read_provider_answer(payload, kind, provider, model)


def list_models(
    provider, base_url, api_key, *, api_format=None, auth_mode=None,
):
    kind, selected_auth = resolve_provider_config(provider, api_format, auth_mode)
    token = (api_key or "").strip()
    if not token:
        raise ValueError("Hãy nhập API key trước khi quét Model.")
    model_base = base_url
    if kind == "gemini" and model_base.rstrip("/").endswith("/openai"):
        model_base = model_base.rstrip("/")[:-7]
    url = api_endpoint(provider_base_url(provider, model_base, kind), kind, "models")
    try:
        response = _request("GET", url, api_headers(kind, token, selected_auth))
    except requests.RequestException as exc:
        raise RuntimeError("Không lấy được danh sách Model. Kiểm tra mạng và Base URL.") from exc
    if not response.ok:
        # Gateways compatible with Claude Code messages frequently omit
        # model discovery. A failed GET /models does not mean POST /messages
        # fails; report the distinction rather than marking the key invalid.
        if provider == "Claude Gateway (AUTH_TOKEN)" and response.status_code in (404, 405, 501):
            raise RuntimeError(
                f"Gateway trả HTTP {response.status_code} cho /v1/models: "
                "có thể không hỗ trợ quét model. Không phải lỗi xác thực. "
                "Hãy nhập Model ID do gateway cấp rồi dùng "
                "'Kiểm tra kết nối API' để thử gửi một tin nhắn thực tế."
            )
        raise _error(response, token, provider)
    try:
        obj = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "API trả về dữ liệu không phải JSON khi quét model. "
            "Nếu đây là Claude Gateway, có thể dùng Model ID thủ công "
            "và kiểm tra kết nối bằng tin nhắn ngắn."
        ) from exc
    if isinstance(obj, dict):
        items = obj.get("data", obj.get("models"))
        if isinstance(items, dict):
            items = items.get("data", items.get("models"))
    elif isinstance(obj, list):
        items = obj
    else:
        items = None
    if not isinstance(items, list):
        raise RuntimeError(
            "Phản hồi /models không chứa danh sách model chuẩn "
            "(data hoặc models dạng mảng). Gateway có thể chỉ hỗ trợ "
            "/v1/messages. Hãy nhập Model ID thủ công và dùng "
            "'Kiểm tra kết nối API' thay vì quét model."
        )
    models = []
    for item in items:
        if isinstance(item, str) and item.strip():
            models.append(item.strip())
        elif isinstance(item, dict):
            if kind == "gemini":
                methods = item.get("supportedGenerationMethods")
                if isinstance(methods, list) and "generateContent" not in methods:
                    continue
                value = item.get("name") or item.get("baseModelId") or item.get("id")
                if isinstance(value, str) and value.startswith("models/"):
                    value = value[7:]
            else:
                value = item.get("id") or item.get("name")
            if isinstance(value, str) and value.strip():
                models.append(value.strip())
    return sorted(set(models), key=str.casefold)[:300]

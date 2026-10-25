"""Authenticated, encrypted, opt-in Supabase persistence for Streamlit.

All database requests use the signed-in user's JWT (not a service-role key).
RLS policies restrict each account to its own row. API credentials are encrypted
with a Fernet key held only in server-side Streamlit secrets.
"""
import hashlib
import json
import re
import time
import uuid

import requests
from cryptography.fernet import Fernet, InvalidToken


CONTENT_FIELDS = (
    "name", "url", "source", "title", "description", "translated",
    "prompts", "metadata", "language", "new_title", "new_description",
    "seo_tags", "saved_order", "saved", "processed", "job_state",
    "job_error", "job_percent", "job_stage",
)
API_WIDGET_PREFIXES = ("api_key_", "api_base_", "api_model_id_")
API_WIDGET_EXACT = ("api_provider", "supadata_api_key_input")
MAX_BYTES = 7 * 1024 * 1024


def configured(secrets):
    required = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SESSION_ENCRYPTION_KEY")
    return all(str(secrets.get(name, "")).strip() for name in required)


def get_config(secrets):
    if not configured(secrets):
        raise ValueError("Chưa cấu hình Supabase và khóa mã hóa trong Streamlit Secrets.")
    url = str(secrets["SUPABASE_URL"]).strip().rstrip("/")
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::443)?", url):
        raise ValueError("SUPABASE_URL phải là HTTPS domain, không chứa path hoặc thông tin đăng nhập.")
    key = str(secrets["SUPABASE_ANON_KEY"]).strip()
    # Never allow privileged secret/service-role credentials: they bypass RLS.
    if key.startswith("sb_secret_"):
        raise ValueError("Hãy dùng Supabase publishable key, không dùng secret key.")
    encryption_key = str(secrets["SESSION_ENCRYPTION_KEY"]).strip()
    try:
        cipher = Fernet(encryption_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise ValueError("SESSION_ENCRYPTION_KEY chưa phải khóa Fernet hợp lệ.") from exc
    return url, key, cipher


def _request(method, endpoint, headers, **kwargs):
    try:
        response = requests.request(
            method, endpoint, headers=headers, timeout=(8, 22),
            allow_redirects=False, **kwargs
        )
    except requests.RequestException as exc:
        raise RuntimeError("Không thể kết nối cơ sở dữ liệu tài khoản. Hãy kiểm tra mạng.") from exc
    if not 200 <= response.status_code < 300:
        try:
            payload = response.json()
            detail = payload.get("msg") or payload.get("message") or payload.get("error_description") or payload.get("error") or ""
        except (ValueError, AttributeError):
            detail = ""
        raise RuntimeError(
            f"Lưu trữ / đăng nhập trả HTTP {response.status_code}: "
            f"{str(detail)[:220] or 'kiểm tra tài khoản, cấu hình Supabase và RLS'}"
        )
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("Cơ sở dữ liệu trả phản hồi không phải JSON.") from exc


def _anon_headers(anon_key):
    # Publishable keys are not JWTs. Send on apikey, not as a Bearer token.
    # Signed-in Data API calls instead use the user's access_token as Bearer.
    return {"apikey": anon_key, "Content-Type": "application/json"}


def sign_in(secrets, email, password):
    url, anon, _ = get_config(secrets)
    body = {"email": email.strip().lower(), "password": password}
    response = _request(
        "POST", url + "/auth/v1/token?grant_type=password",
        _anon_headers(anon), json=body
    )
    if not isinstance(response, dict) or not response.get("access_token"):
        raise RuntimeError("Không nhận được phiên đăng nhập từ Supabase.")
    return _auth_details(response)


def sign_up(secrets, email, password):
    url, anon, _ = get_config(secrets)
    return _request(
        "POST", url + "/auth/v1/signup", _anon_headers(anon),
        json={"email": email.strip().lower(), "password": password}
    )


def _auth_details(data):
    user = data.get("user", {})
    uid = user.get("id", "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", str(uid)):
        raise RuntimeError("Supabase không trả mã tài khoản hợp lệ.")
    return {
        "user_id": uid,
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": time.time() + max(60, int(data.get("expires_in", 3600))) - 45,
        "email": user.get("email", ""),
    }


def refresh_auth(secrets, session):
    if time.time() < session["expires_at"]:
        return session
    if not session.get("refresh_token"):
        raise RuntimeError("Phiên đăng nhập đã hết hạn; hãy đăng nhập lại.")
    url, anon, _ = get_config(secrets)
    data = _request(
        "POST", url + "/auth/v1/token?grant_type=refresh_token",
        _anon_headers(anon), json={"refresh_token": session["refresh_token"]}
    )
    updated = _auth_details(data)
    if updated["user_id"] != session["user_id"]:
        raise RuntimeError("Tài khoản đăng nhập đã thay đổi, từ chối tải dữ liệu.")
    return updated


def _user_headers(anon, session):
    return {
        "apikey": anon,
        "Authorization": "Bearer " + session["access_token"],
        "Content-Type": "application/json",
    }


def normalize_sessions(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("workspaces", {}), dict):
        raise ValueError("Dữ liệu phiên đã lưu không hợp lệ.")
    items = raw.get("workspaces", {})
    if len(items) > 150:
        raise ValueError("Vượt giới hạn 150 phiên.")
    workspaces = {}
    for ident, record in items.items():
        if not isinstance(ident, str) or not re.fullmatch(r"[a-f0-9]{32}", ident):
            continue
        if not isinstance(record, dict):
            continue
        copy = {}
        for field in CONTENT_FIELDS:
            val = record.get(field)
            if field in ("saved_order", "job_percent"):
                copy[field] = int(val) if isinstance(val, int) and 0 <= val < 10**7 else 0
            elif field in ("saved", "processed"):
                copy[field] = bool(val)
            elif isinstance(val, str):
                if len(val) > 400000:
                    raise ValueError("Nội dung phiên quá lớn.")
                copy[field] = val
        if copy.get("job_state") == "running":
            copy["job_state"] = "interrupted"
            copy["job_error"] = "Máy chủ hoặc kết nối trước đã dừng; hãy chạy lại phiên."
        workspaces[ident] = copy
    selected = raw.get("selected_session")
    return {
        "workspaces": workspaces,
        "selected_session": selected if selected in workspaces else next(iter(workspaces), None),
        "saved_session_order": max(
            int(raw.get("saved_session_order", 0))
            if isinstance(raw.get("saved_session_order", 0), int) else 0,
            *(x.get("saved_order", 0) for x in workspaces.values()), 0
        ),
        "version": 1,
    }


def backup_state(workspaces, selected_session, saved_session_order):
    raw = {
        "workspaces": workspaces, "selected_session": selected_session,
        "saved_session_order": saved_session_order,
    }
    clean = normalize_sessions(raw)
    encoded = json.dumps(clean, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise ValueError("Dữ liệu phiên quá lớn (hơn 7 MB). Hãy chia nhỏ nội dung.")
    return clean


def settings_from_widgets(state):
    out = {}
    for key in list(state):
        if key in API_WIDGET_EXACT or key.startswith(API_WIDGET_PREFIXES):
            value = state.get(key)
            if isinstance(value, str) and len(value) < 10000:
                out[key] = value
    return out


def restore_widget_settings(state, settings):
    if not isinstance(settings, dict):
        return
    for name, value in settings.items():
        if (name in API_WIDGET_EXACT or name.startswith(API_WIDGET_PREFIXES)) and isinstance(value, str):
            if len(value) < 10000:
                state[name] = value


def save_user(secrets, auth, payload, settings):
    url, anon, cipher = get_config(secrets)
    blob = json.dumps(settings, ensure_ascii=False).encode("utf-8")
    if len(blob) > 120000:
        raise ValueError("Cấu hình API quá lớn.")
    secret_blob = cipher.encrypt(blob).decode("ascii")
    body = [{
        "user_id": auth["user_id"], "payload": payload,
        "encrypted_config": secret_blob
    }]
    _request(
        "POST", url + "/rest/v1/youtube_studio_state",
        {**_user_headers(anon, auth),
         "Prefer": "resolution=merge-duplicates,return=minimal"},
        json=body,
    )


def load_user(secrets, auth):
    url, anon, cipher = get_config(secrets)
    uid = auth["user_id"]
    data = _request(
        "GET", url + "/rest/v1/youtube_studio_state",
        _user_headers(anon, auth),
        params={"select": "payload,encrypted_config", "user_id": "eq." + uid, "limit": "1"}
    )
    if not data:
        return None, {}
    if not isinstance(data, list) or not isinstance(data[0], dict):
        raise RuntimeError("Dữ liệu Supabase không đúng cấu trúc.")
    item = data[0]
    payload = normalize_sessions(item["payload"])
    encrypted = item.get("encrypted_config")
    if not encrypted:
        return payload, {}
    try:
        settings = json.loads(cipher.decrypt(encrypted.encode("ascii")).decode("utf-8"))
    except (ValueError, InvalidToken, TypeError) as exc:
        raise RuntimeError(
            "Không giải mã được cài đặt API. Kiểm tra khóa SESSION_ENCRYPTION_KEY trong Secrets."
        ) from exc
    return payload, settings


def snapshot_hash(payload, settings):
    encoded = json.dumps(
        {"payload": payload, "settings": settings},
        ensure_ascii=False, sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

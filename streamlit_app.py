import json
import hashlib
import re
import uuid
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import streamlit.components.v1 as components
from streamlit.runtime import exists as streamlit_runtime_exists

import requests
from faithful_summary import translate_part_faithfully, OPTIMIZATION_VERSION, source_hash
from provider_retries import retry_transient_provider
from character_profiles import MAX_DETAILED_CHARACTERS
from server_character_jobs import (
    profile_job, start_character_job, collect_character_jobs,
)
import streamlit as st
from PIL import Image
from youtube_transcript_api import YouTubeTranscriptApi
from api_clients import (PROVIDERS, TransientProviderError, generate_text, list_models,
                         validate_base_url, migrate_claude_settings,
                         migrate_free_provider_settings)
from background_jobs import JobProgress, run_full_job
from server_video_jobs import run_video_forms_job, run_full_job_with_server_saves
from server_video_jobs import _persist_lock
from background_registry import JobRegistry
from transcript_sources import parse_uploaded_subtitles
from persistent_store import (
    backup_state, configured, get_config, sign_in, sign_up,
    load_user, refresh_auth, save_user, settings_from_widgets,
    remember_widget_settings, activate_provider_settings,
    activate_shared_api_settings, restore_widget_settings,
    snapshot_hash, normalize_sessions,
)
from browser_session_store import (
    STORAGE_KEY, API_SETTINGS_STORAGE_KEY,
    encode_browser_backup, decode_browser_backup,
)
from copy_buttons import copy_all_button
from video_forms_ui import render_video_forms
from video_scene_planner import character_bible_prompt, parse_json_object
from section_retries import rerun_translation, rerun_seo, portrait_retry_specs, prepare_reviewed_script
from character_images import (IMAGE_STORE, IMAGE_MODEL, session_images_zip, create_character_png,
    detailed_character_profiles, character_reference_description, character_profile_text, CHARACTER_PROFILE_FIELDS)
from session_name_controls import session_name_control, rename_record
from durable_queue import (queue_available, worker_healthy, submit_job,
    get_owned_jobs, apply_owned_job_results, fetch_portrait_images)

st.set_page_config(page_title="LMT Studio Pro", page_icon="🎬", layout="wide")
st.title("🎬 LMT Studio Pro")
st.caption("Phụ đề YouTube • Dịch đa ngôn ngữ • SEO • Thumbnail gốc • Quản lý phiên")

# Disable mouse-hover explanations throughout the app. Labels, click-based
# controls (including advanced options), and screen-reader accessible names
# remain unchanged.
st.markdown(
    """
    <style>
    [data-baseweb="tooltip"],
    [role="tooltip"],
    [data-testid="stTooltipContent"],
    [data-testid="stTooltipHoverTarget"] {
        display: none !important;
    }
    /* Scope blue styling ONLY to the original-thumbnail download button. */
    .st-key-original_thumbnail_download [data-testid="stDownloadButton"] button {
        background-color: #2563eb !important;
        border-color: #2563eb !important;
        color: #fff !important;
    }
    .st-key-original_thumbnail_download [data-testid="stDownloadButton"] button:hover {
        background-color: #1d4ed8 !important;
        border-color: #1d4ed8 !important;
        color: #fff !important;
    }
    /* Only the two result tabs: distinct outlined tap targets with a gap. */
    .st-key-result_tabs [data-testid="stTabs"] [role="tablist"] {
        gap: 16px !important;
        padding: 6px 2px 12px !important;
        border-bottom: 0 !important;
    }
    .st-key-result_tabs [data-testid="stTabs"] [role="tab"] {
        min-height: 54px !important;
        padding: 12px 20px !important;
        border: 2px solid #94a3b8 !important;
        border-radius: 12px !important;
        background-color: #f8fafc !important;
        color: #1e293b !important;
        font-weight: 700 !important;
        white-space: normal !important;
        text-align: center !important;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08) !important;
    }
    .st-key-result_tabs [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        border-color: #2563eb !important;
        background-color: #eff6ff !important;
        color: #1d4ed8 !important;
        box-shadow: 0 0 0 1px #2563eb !important;
    }
    .st-key-result_tabs [data-testid="stTabs"] [role="tab"][aria-selected="false"]:hover {
        border-color: #64748b !important;
        background-color: #e2e8f0 !important;
    }
    .st-key-result_tabs [data-testid="stTabs"] [role="tab"]:focus-visible {
        outline: 3px solid #60a5fa !important;
        outline-offset: 3px !important;
    }
    /* Replace the thin default active underline with the full button border. */
    .st-key-result_tabs [data-testid="stTabs"] [data-baseweb="tab-highlight"],
    .st-key-result_tabs [data-testid="stTabs"] [data-baseweb="tab-border"] {
        display: none !important;
    }
    @media (max-width: 640px) {
        .st-key-result_tabs [data-testid="stTabs"] [role="tablist"] {
            gap: 12px !important;
        }
        .st-key-result_tabs [data-testid="stTabs"] [role="tab"] {
            padding: 12px 14px !important;
            min-height: 56px !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

LANGUAGES = [
    "Tiếng Ba Lan", "Tiếng Anh", "Tiếng Pháp", "Tiếng Đức", "Tiếng Tây Ban Nha",
    "Tiếng Ý", "Tiếng Bồ Đào Nha", "Tiếng Hà Lan", "Tiếng Thụy Điển",
    "Tiếng Na Uy", "Tiếng Đan Mạch", "Tiếng Phần Lan", "Tiếng Iceland",
    "Tiếng Séc", "Tiếng Slovakia", "Tiếng Hungary", "Tiếng Romania",
    "Tiếng Bulgaria", "Tiếng Hy Lạp", "Tiếng Croatia", "Tiếng Serbia",
    "Tiếng Slovenia", "Tiếng Bosnia", "Tiếng Albania", "Tiếng Lithuania",
    "Tiếng Latvia", "Tiếng Estonia", "Tiếng Ukraine", "Tiếng Nga",
    "Tiếng Belarus", "Tiếng Thổ Nhĩ Kỳ", "Tiếng Ireland", "Tiếng Malta",
    "Tiếng Catalan", "Tiếng Basque", "Tiếng Wales", "Tiếng Luxembourg",
    "Tiếng Macedonia", "Tiếng Việt", "Tiếng Nhật", "Tiếng Hàn",
]
FIELDS = ("url", "source", "title", "description", "translated", "prompts", "metadata", "language", "new_title", "new_description", "seo_tags", "video_forms", "optimized_script", "optimization_review_json", "character_images_error", "character_bible", "character_images_manifest", "character_profile_json", "seo_stale", "character_bible_stale")
FORM_FIELDS = ("url", "language")


def blank_session(name):
    return {
        "name": name, "url": "", "source": "", "title": "", "description": "",
        "translated": "", "prompts": "", "metadata": "", "language": "Tiếng Ba Lan",
        "saved": False, "processed": False, "saved_order": 0,
        "new_title": "", "new_description": "", "seo_tags": "", "video_forms": "", "optimized_script": "", "optimization_review_json": "", "character_images_error": "", "character_bible": "", "character_images_manifest": "", "character_profile_json": "", "seo_stale": False, "character_bible_stale": False,
    }


def unique_name(requested):
    existing = {p["name"].casefold() for p in st.session_state.workspaces.values()}
    base = (requested or "Phiên mới").strip()[:80] or "Phiên mới"
    name = base
    i = 2
    while name.casefold() in existing:
        name = f"{base} ({i})"
        i += 1
    return name


def sync_form(sid):
    """Read current widget values before creating, downloading or switching a session."""
    record = st.session_state.workspaces[sid]
    for field in FORM_FIELDS:
        widget_key = f"field_{sid}_{field}"
        if widget_key in st.session_state:
            record[field] = st.session_state[widget_key]


# Optional durable storage. When Supabase is not configured, users can
# still use local browser-session mode and export a private JSON backup.
try:
    CLOUD_ENABLED = configured(st.secrets)
except (FileNotFoundError, OSError):
    CLOUD_ENABLED = False
try:
    DURABLE_QUEUE_ENABLED = bool(CLOUD_ENABLED and queue_available(st.secrets))
except (FileNotFoundError, OSError):
    DURABLE_QUEUE_ENABLED = False



def _cloud_secrets():
    return st.secrets


def _refresh_login():
    if not CLOUD_ENABLED or "cloud_auth" not in st.session_state:
        return None
    updated = refresh_auth(_cloud_secrets(), st.session_state.cloud_auth)
    st.session_state.cloud_auth = updated
    return updated


if CLOUD_ENABLED:
    if not st.session_state.get("cloud_auth"):
        st.info(
            "🔐 Đăng nhập để giữ lại các phiên, bản dịch và cấu hình API "
            "cho những lần mở ứng dụng sau."
        )
        sign_in_tab, create_account_tab = st.tabs(
            ["🔑 Đăng nhập", "➕ Tạo tài khoản"]
        )
        with sign_in_tab:
            with st.form("studio_sign_in"):
                login_email = st.text_input("Email đăng nhập", key="login_email")
                login_password = st.text_input(
                    "Mật khẩu", type="password", key="login_password"
                )
                do_login = st.form_submit_button(
                    "Đăng nhập và mở phiên đã lưu", use_container_width=True
                )
            if do_login:
                try:
                    identity = sign_in(_cloud_secrets(), login_email, login_password)
                    profile, api_config = load_user(_cloud_secrets(), identity)
                    st.session_state.cloud_auth = identity
                    st.session_state["_cloud_restore"] = {
                        "profile": profile, "api": api_config
                    }
                    st.rerun()
                except Exception as exc:
                    st.error(f"Không thể đăng nhập/tải dữ liệu: {exc}")
        with create_account_tab:
            with st.form("studio_sign_up"):
                new_email = st.text_input("Email", key="signup_email")
                new_password = st.text_input(
                    "Mật khẩu (tối thiểu 8 ký tự)",
                    type="password", key="signup_password"
                )
                register = st.form_submit_button(
                    "Tạo tài khoản", use_container_width=True
                )
            if register:
                if len(new_password) < 8:
                    st.error("Mật khẩu phải có ít nhất 8 ký tự.")
                else:
                    try:
                        sign_up(_cloud_secrets(), new_email, new_password)
                        st.success(
                            "Đã gửi yêu cầu tạo tài khoản. Nếu Supabase yêu cầu "
                            "xác nhận email, hãy kiểm tra hộp thư rồi đăng nhập."
                        )
                    except Exception as exc:
                        st.error(str(exc))
        st.stop()
    try:
        _refresh_login()
    except Exception as exc:
        st.error(
            f"Phiên đăng nhập hoặc kết nối lưu trữ có vấn đề: {exc}. "
            "Hãy đăng xuất rồi đăng nhập lại."
        )
        if st.button("Đăng xuất và đăng nhập lại"):
            st.session_state.clear()
            st.rerun()
        st.stop()


def _restore_cloud_profile():
    pending = st.session_state.pop("_cloud_restore", None)
    if pending is None:
        return
    profile = pending.get("profile")
    if profile:
        workspaces = {}
        for session_id, row in profile["workspaces"].items():
            blank = blank_session(row.get("name", "Phiên đã lưu"))
            blank.update(row)
            workspaces[session_id] = blank
        if workspaces:
            st.session_state.workspaces = workspaces
            st.session_state.selected_session = profile["selected_session"]
            st.session_state.saved_session_order = profile["saved_session_order"]
    api_config = pending.get("api", {})
    restore_widget_settings(st.session_state, api_config)
    st.session_state["_cloud_saved_hash"] = (
        snapshot_hash(profile, api_config) if profile is not None else ""
    )


_restore_cloud_profile()
# Preserve API key and model values from the former 'Anthropic Claude' label.
migrate_claude_settings(st.session_state)
migrate_free_provider_settings(st.session_state)
# Streamlit may prune widgets from the previous page during navigation.
# Restore Supadata and selected-provider values before rendering those inputs.
activate_shared_api_settings(st.session_state)


def _save_cloud_state_unlocked(force=False):
    """Save results plus encrypted per-provider API settings for this user."""
    if not CLOUD_ENABLED or not st.session_state.get("cloud_auth"):
        return
    active = st.session_state.get("selected_session")
    if active in st.session_state.get("workspaces", {}):
        sync_form(active)
    payload = backup_state(
        st.session_state.workspaces, active,
        st.session_state.get("saved_session_order", 0)
    )
    settings = remember_widget_settings(st.session_state)
    fingerprint = snapshot_hash(payload, settings)
    if fingerprint == st.session_state.get("_cloud_saved_hash"):
        return
    try:
        auth = _refresh_login()
        save_user(_cloud_secrets(), auth, payload, settings)
        st.session_state["_cloud_saved_hash"] = fingerprint
        st.session_state.pop("_cloud_save_error", None)
    except Exception as exc:
        st.session_state["_cloud_save_error"] = str(exc)[:350]
        if force:
            raise


def _save_cloud_state(force=False):
    # Serialize browser saves with server checkpoints. Collect the latest
    # character result before writing the user's complete workspace payload.
    with _persist_lock:
        if "collect_profile_background_jobs" in globals():
            if collect_profile_background_jobs():
                st.session_state["_profile_ui_refresh_pending"] = True
        _save_cloud_state_unlocked(force=force)


def _persist_and_rerun():
    try:
        _save_cloud_state(force=True)
    except Exception as exc:
        st.error(
            "Không thể lưu dữ liệu trước khi chuyển phiên. "
            "Thay đổi vẫn đang ở phiên tạm. " + str(exc)
        )
        return
    st.rerun()


# Without Supabase, session content and encrypted API configuration live in
# separate origin-scoped browser stores. Session backups never contain keys.
@st.cache_resource
def _browser_component():
    return components.declare_component(
        "lmt_browser_session_backup",
        path=str(Path(__file__).parent / "browser_sessions_frontend"),
    )


BROWSER_LOCAL_ENABLED = not CLOUD_ENABLED and streamlit_runtime_exists()

# Hydrate saved API widgets before their initial rendering. The encrypted
# browser record uses a non-exportable, browser-only AES key stored in IndexedDB.
if BROWSER_LOCAL_ENABLED and not st.session_state.get("_browser_api_restored"):
    restored_api = _browser_component()(
        mode="api_read", storageKey=API_SETTINGS_STORAGE_KEY,
        key="browser_api_settings_loader", default=None,
    )
    if restored_api is None:
        st.caption("🔐 Đang khôi phục cấu hình API đã lưu trên trình duyệt...")
        st.stop()
    st.session_state["_browser_api_restored"] = True
    if restored_api.get("ok") and isinstance(restored_api.get("settings"), dict):
        restore_widget_settings(st.session_state, restored_api["settings"])
    else:
        st.session_state["_browser_api_storage_disabled"] = True
        st.session_state["_browser_api_error"] = restored_api.get(
            "message", "Không đọc được cấu hình API trên trình duyệt."
        )
    st.rerun()

if BROWSER_LOCAL_ENABLED and not st.session_state.get("_browser_sessions_restored"):
    stored = _browser_component()(
        mode="read", storageKey=STORAGE_KEY,
        key="browser_session_loader", default=None,
    )
    if stored is None:
        st.caption("💾 Đang khôi phục các phiên đã lưu trong trình duyệt...")
        if st.button("Tiếp tục không dùng bộ nhớ trình duyệt"):
            st.session_state["_browser_sessions_restored"] = True
            st.session_state["_browser_sessions_disabled"] = True
            st.rerun()
        st.stop()
    st.session_state["_browser_sessions_restored"] = True
    if stored.get("ok") and stored.get("value"):
        try:
            restored = decode_browser_backup(stored["value"])
            st.session_state.workspaces = {
                ident: {**blank_session(rec.get("name", "Phiên đã lưu")), **rec}
                for ident, rec in restored["workspaces"].items()
            }
            st.session_state.selected_session = restored["selected_session"]
            st.session_state.saved_session_order = restored["saved_session_order"]
            st.session_state["_browser_restore_success"] = True
        except (ValueError, TypeError) as exc:
            st.session_state["_browser_restore_error"] = str(exc)
            st.session_state["_browser_sessions_disabled"] = True
    elif not stored.get("ok"):
        st.session_state["_browser_restore_error"] = stored.get(
            "message", "Trình duyệt không cho phép sử dụng localStorage."
        )
        st.session_state["_browser_sessions_disabled"] = True
    st.rerun()


def _save_browser_sessions():
    """Save current sessions and confirm deletion in the active browser.

    With Supabase, its row is the source of truth; after a session deletion,
    purge a leftover anonymous browser snapshot to prevent old local copies
    from reappearing if cloud persistence is later disabled.
    """
    revision = st.session_state.get("_browser_delete_revision")
    if not BROWSER_LOCAL_ENABLED and not (CLOUD_ENABLED and revision):
        return
    if st.session_state.get("_browser_sessions_disabled"):
        if revision:
            st.session_state["_browser_save_error"] = (
                "Trình duyệt từ chối ghi/xóa bộ nhớ. Phiên đã được xóa trong "
                "app nhưng chưa thể xác nhận cập nhật bản lưu trình duyệt."
            )
        return
    if CLOUD_ENABLED and st.session_state.get("_cloud_save_error"):
        # Never acknowledge deletion of a stale local copy before Supabase
        # confirms the reduced set of sessions was saved successfully.
        return
    selected = st.session_state.get("selected_session")
    if BROWSER_LOCAL_ENABLED and selected in st.session_state.get("workspaces", {}):
        sync_form(selected)
    try:
        kwargs = {
            "storageKey": STORAGE_KEY,
            "key": "browser_session_writer",
            "default": None,
        }
        if revision:
            kwargs["revision"] = revision
        if CLOUD_ENABLED:
            kwargs["mode"] = "remove"
        else:
            state = backup_state(
                st.session_state.workspaces, selected,
                st.session_state.get("saved_session_order", 0),
            )
            kwargs["mode"] = "write"
            kwargs["payload"] = encode_browser_backup(state)
        outcome = _browser_component()(**kwargs)
        if isinstance(outcome, dict) and not outcome.get("ok", True):
            st.session_state["_browser_save_error"] = outcome.get(
                "message", "Trình duyệt không cho phép cập nhật bản lưu."
            )
            st.session_state["_browser_sessions_disabled"] = True
        elif (
            revision and isinstance(outcome, dict)
            and outcome.get("ok") and outcome.get("revision") == revision
        ):
            st.session_state.pop("_browser_delete_revision", None)
            st.session_state.pop("_browser_save_error", None)
            st.session_state["_browser_delete_confirmed"] = True
    except (ValueError, TypeError) as exc:
        st.session_state["_browser_save_error"] = str(exc)
        st.session_state["_browser_sessions_disabled"] = True


def _save_browser_api_settings():
    """Persist only allowlisted settings as AES-GCM ciphertext on this browser.

    Provider keys must never join session backups or plaintext localStorage.
    A failed browser storage operation leaves the live widgets untouched.
    """
    settings = remember_widget_settings(st.session_state)
    if not BROWSER_LOCAL_ENABLED or st.session_state.get("_browser_api_storage_disabled"):
        return
    fingerprint = snapshot_hash({}, settings)
    if fingerprint == st.session_state.get("_browser_api_saved_hash"):
        return
    try:
        outcome = _browser_component()(
            mode="api_write", storageKey=API_SETTINGS_STORAGE_KEY,
            payload=json.dumps(settings, ensure_ascii=False, sort_keys=True),
            revision=fingerprint, key="browser_api_settings_writer", default=None,
        )
        if isinstance(outcome, dict):
            if outcome.get("ok") and outcome.get("revision") == fingerprint:
                st.session_state["_browser_api_saved_hash"] = fingerprint
                st.session_state.pop("_browser_api_error", None)
            elif not outcome.get("ok", True):
                st.session_state["_browser_api_storage_disabled"] = True
                st.session_state["_browser_api_error"] = outcome.get(
                    "message", "Trình duyệt không thể lưu cấu hình API."
                )
    except (TypeError, ValueError) as exc:
        st.session_state["_browser_api_storage_disabled"] = True
        st.session_state["_browser_api_error"] = "Không thể lưu cấu hình API trên trình duyệt."


# Data belong to this browser's current Streamlit session, never a shared server file.
if "workspaces" not in st.session_state:
    first = uuid.uuid4().hex
    record = blank_session("Phiên 1")
    # Preserve data in an existing browser session after a hot-reload from an older app.
    for field in ("source", "translated", "prompts", "metadata"):
        value = st.session_state.get(field, "")
        if isinstance(value, str):
            record[field] = value
    st.session_state.workspaces = {first: record}
    st.session_state.selected_session = first

if "background_jobs" not in st.session_state:
    st.session_state.background_jobs = {}
if "video_background_jobs" not in st.session_state:
    st.session_state.video_background_jobs = {}
if "profile_background_jobs" not in st.session_state:
    st.session_state.profile_background_jobs = {}



@st.cache_resource
def get_job_executor():
    # Shared worker pool, not tied to any one browser connection.
    return ThreadPoolExecutor(max_workers=3, thread_name_prefix="youtube-translation")


@st.cache_resource
def get_job_registry():
    # Keep active Futures accessible when a browser tab disconnects and returns.
    # This process-local registry does NOT survive Streamlit server restart.
    return JobRegistry()


def _job_scope():
    auth = st.session_state.get("cloud_auth") if CLOUD_ENABLED else None
    if isinstance(auth, dict) and auth.get("user_id"):
        return "account:" + str(auth["user_id"])
    return "browser"


def _video_job_scope():
    return "video:" + _job_scope()


def collect_profile_background_jobs():
    return collect_character_jobs(
        st.session_state.workspaces, st.session_state.profile_background_jobs,
        get_job_registry(), "characters:" + _job_scope(),
    )


def sync_durable_queue():
    """Read worker checkpoints after browser or Streamlit restart."""
    if not DURABLE_QUEUE_ENABLED:
        return False
    try:
        changed = apply_owned_job_results(
            st.session_state.workspaces,
            get_owned_jobs(st.secrets, _refresh_login()),
        )
        st.session_state.pop("_durable_queue_error", None)
        return changed
    except Exception as exc:
        st.session_state["_durable_queue_error"] = str(exc)[:250]
        return False


def ensure_durable_worker_available():
    if DURABLE_QUEUE_ENABLED and not worker_healthy(st.secrets, _refresh_login()):
        raise RuntimeError(
            "Worker độc lập chưa hoạt động (không có heartbeat mới). "
            "Hãy triển khai worker để chạy qua đêm."
        )


def reattach_video_background_jobs():
    jobs = st.session_state.video_background_jobs
    for session_id, record in st.session_state.workspaces.items():
        if session_id in jobs or record.get("video_job_state") != "running":
            continue
        run_id = record.get("video_job_run_id")
        if run_id:
            job = get_job_registry().lookup(
                run_id, session_id, _video_job_scope()
            )
            if job:
                jobs[session_id] = job
            else:
                # Server may have restarted; do not promise background
                # completion when its process-local Future is gone.
                record["video_job_state"] = "interrupted"
                record["video_job_error"] = (
                    "Máy chủ đã khởi động lại hoặc tác vụ không còn hoạt động. "
                    "Hãy nhấn Chạy lại riêng để tiếp tục từ form đã lưu."
                )


def collect_video_background_jobs():
    changed = False
    for session_id, job in list(st.session_state.video_background_jobs.items()):
        record = st.session_state.workspaces.get(session_id)
        if not record or record.get("video_job_run_id") != job["run_id"]:
            get_job_registry().cancel(
                job["run_id"], session_id, _video_job_scope()
            )
            job["progress"].cancel()
            st.session_state.video_background_jobs.pop(session_id, None)
            continue
        for field, value in job["progress"].partial_result().items():
            if field == "video_forms" and record.get(field) != value:
                record[field] = value
                changed = True
        percentage, stage = job["progress"].snapshot()
        if record.get("video_job_percent") != percentage or record.get("video_job_stage") != stage:
            record["video_job_percent"] = percentage
            record["video_job_stage"] = stage
            changed = True
        if not job["future"].done():
            continue
        try:
            outcome = job["future"].result()
        except Exception:
            outcome = {"ok": False, "fields": {},
                       "error": "Tác vụ nền kết thúc ngoài dự kiến."}
        for field, value in outcome.get("fields", {}).items():
            if field == "video_forms":
                record[field] = value
        record["video_job_state"] = "completed" if outcome.get("ok") else "failed"
        record["video_job_error"] = "" if outcome.get("ok") else outcome.get("error", "")
        record["video_job_percent"] = 100 if outcome.get("ok") else percentage
        record["video_job_run_id"] = ""
        record["processed"] = True
        record["saved"] = True
        st.session_state.video_background_jobs.pop(session_id, None)
        get_job_registry().discard(job["run_id"], session_id, _video_job_scope())
        changed = True
    return changed


def reattach_background_jobs():
    """Reattach worker references from restored workspaces, using opaque run IDs."""
    jobs = st.session_state.background_jobs
    scope = _job_scope()
    for session_id, record in st.session_state.workspaces.items():
        if session_id in jobs or record.get("job_state") not in ("running", "interrupted"):
            continue
        run_id = record.get("job_run_id")
        if not run_id:
            continue
        job = get_job_registry().lookup(run_id, session_id, scope)
        if job:
            jobs[session_id] = job
            record["job_state"] = "running"
            record["job_error"] = ""


# Existing workspaces may come from older versions; only completed work is saved.
if "saved_session_order" not in st.session_state:
    st.session_state.saved_session_order = 0
for _id, _rec in st.session_state.workspaces.items():
    old_order = _rec.get("saved_order", 0)
    if isinstance(old_order, int) and old_order > 0:
        st.session_state.saved_session_order = max(st.session_state.saved_session_order, old_order)
    if "processed" not in _rec:
        _rec["processed"] = any(
            isinstance(_rec.get(field), str) and _rec[field].strip()
            for field in ("source", "translated", "prompts", "metadata")
        )
    _rec["saved"] = bool(_rec["processed"])
for _id, _rec in st.session_state.workspaces.items():
    if not isinstance(_rec.get("saved_order"), int) or _rec["saved_order"] <= 0:
        st.session_state.saved_session_order += 1
        _rec["saved_order"] = st.session_state.saved_session_order


def mark_session_processed(record):
    """Only successful subtitle extraction, file import, translation or SEO is saved."""
    record["processed"] = True
    record["saved"] = True
    if not isinstance(record.get("saved_order"), int) or record["saved_order"] <= 0:
        st.session_state.saved_session_order += 1
        record["saved_order"] = st.session_state.saved_session_order
    st.session_state["_session_flash"] = "✅ Đã đưa phiên xử lý thành công vào danh sách."


def collect_completed_jobs():
    """Synchronize in-memory worker output with the matching Streamlit session."""
    changed = False
    for session_id, job in list(st.session_state.background_jobs.items()):
        if session_id not in st.session_state.workspaces:
            get_job_registry().cancel(job["run_id"], session_id, _job_scope())
            job["progress"].cancel()
            del st.session_state.background_jobs[session_id]
            continue

        record = st.session_state.workspaces[session_id]
        if record.get("job_run_id") != job["run_id"]:
            get_job_registry().cancel(job["run_id"], session_id, _job_scope())
            job["progress"].cancel()
            del st.session_state.background_jobs[session_id]
            continue

        # Checkpoints are available before the worker has completed its entire job.
        for field, value in job["progress"].partial_result().items():
            if field in FIELDS and record.get(field) != value:
                record[field] = value
                changed = True

        percent, stage = job["progress"].snapshot()
        if record.get("job_percent") != percent or record.get("job_stage") != stage:
            record["job_percent"] = percent
            record["job_stage"] = stage
            changed = True

        future = job["future"]
        if not future.done():
            continue
        del st.session_state.background_jobs[session_id]
        try:
            outcome = future.result()
        except Exception:
            outcome = {"ok": False, "fields": {},
                       "error": "Tác vụ nền gặp lỗi không mong đợi."}
        for field, value in outcome.get("fields", {}).items():
            if field in FIELDS:
                record[field] = value
        if outcome.get("ok"):
            record["job_state"] = "completed"
            record["job_error"] = ""
            mark_session_processed(record)
            st.session_state["_session_flash"] = (
                f"✅ Phiên '{record['name']}' đã hoàn thành; nhấn tên trong danh sách để xem."
            )
        else:
            # A failed attempt must remain accessible even if YouTube returned
            # no subtitles or the provider failed before producing any text.
            record["job_state"] = "failed"
            record["job_error"] = outcome.get("error", "Không rõ nguyên nhân.")
            record["processed"] = True
            record["saved"] = True
            st.session_state["_session_flash"] = (
                f"⚠️ Phiên '{record['name']}' gặp lỗi. "
                "Nhấn tên phiên để xem lý do và chạy lại."
            )
        record["job_run_id"] = ""
        get_job_registry().discard(job["run_id"], session_id, _job_scope())
        changed = True
    return changed


def archive_previous_session(session_id):
    """Keep a completed session accessible before switching to a new blank one."""
    if session_id not in st.session_state.workspaces:
        return False
    # Sync current URL and target language from Streamlit widgets first.
    sync_form(session_id)
    previous = st.session_state.workspaces[session_id]
    # A URL alone or an empty session is not considered a completed run.
    has_result = any(
        isinstance(previous.get(field), str) and previous[field].strip()
        for field in (
            "source", "translated", "prompts", "metadata",
            "new_title", "new_description", "seo_tags",
        )
    )
    if not has_result:
        return False
    previous["processed"] = True
    previous["saved"] = True
    if not isinstance(previous.get("saved_order"), int) or previous["saved_order"] <= 0:
        st.session_state.saved_session_order += 1
        previous["saved_order"] = st.session_state.saved_session_order
    return True


def _clear_session_widgets(session_id):
    """Remove any inputs and transient data tied to this single session.

    Provider API keys/settings belong to the user, not to a video session,
    so they are explicitly not touched by deletion.
    """
    named_widgets = {
        f"field_{session_id}_url",
        f"field_{session_id}_language",
        f"inline_session_name_{session_id}",
    }
    prefixes = (f"thumb_{session_id}_",)
    for widget_key in list(st.session_state):
        if widget_key in named_widgets or widget_key.startswith(prefixes):
            st.session_state.pop(widget_key, None)



def delete_saved_session(session_id):
    """Remove one owned session and its job, without touching provider keys."""
    if session_id not in st.session_state.workspaces:
        return
    old = st.session_state.workspaces[session_id]
    get_job_registry().cancel(old.get("job_run_id"), session_id, _job_scope())
    get_job_registry().cancel(old.get("video_job_run_id"), session_id, _video_job_scope())
    get_job_registry().cancel(
        profile_job(old).get("run_id"), session_id, "characters:" + _job_scope(),
    )
    st.session_state.profile_background_jobs.pop(session_id, None)
    video_job = st.session_state.video_background_jobs.pop(session_id, None)
    if video_job:
        video_job["progress"].cancel()
        video_job["future"].cancel()
    IMAGE_STORE.clear(_job_scope(), session_id)
    job = st.session_state.background_jobs.pop(session_id, None)
    if job:
        job["progress"].cancel()
        job["future"].cancel()
    del st.session_state.workspaces[session_id]
    _clear_session_widgets(session_id)
    st.session_state["_browser_delete_revision"] = uuid.uuid4().hex
    st.session_state.pop("_browser_delete_confirmed", None)
    if not st.session_state.workspaces:
        new_id = uuid.uuid4().hex
        st.session_state.saved_session_order += 1
        new_record = blank_session("Phiên mới")
        new_record["saved_order"] = st.session_state.saved_session_order
        st.session_state.workspaces[new_id] = new_record
    if st.session_state.selected_session == session_id:
        active = max(
            st.session_state.workspaces,
            key=lambda k: st.session_state.workspaces[k].get("saved_order", 0),
        )
        st.session_state.selected_session = active
        st.session_state["_open_session_next"] = active
    st.session_state["confirm_delete_session_id"] = None
    st.session_state["_session_flash"] = (
        "Đã xóa phiên cùng kết quả, kịch bản và form video liên quan."
    )


# On a rerun after creating or opening a session, set the active session directly.
# The saved-session buttons are the only navigation controls; no top dropdown.
if "_open_session_next" in st.session_state:
    st.session_state.selected_session = st.session_state.pop("_open_session_next")

# Reconnect to a still-running Future after Streamlit creates a fresh session
# for a reloaded browser tab, then collect any finished work.
reattach_background_jobs()
collect_completed_jobs()
reattach_video_background_jobs()
collect_video_background_jobs()
collect_profile_background_jobs()
sync_durable_queue()

# Use two independent views inside ONE Streamlit entrypoint. Unlike page_link,
# this needs no page registry, so Cloud cannot raise StreamlitPageNotFoundError.
with st.sidebar:
    st.markdown("**🧭 Ứng dụng**")
    selected_app = st.radio(
        "Chọn ứng dụng",
        ("🎬 YouTube Translator", "🎙️ AI33 / OpenSpeaker"),
        key="_lmt_selected_app",
        label_visibility="collapsed",
    )
    st.divider()

if selected_app == "🎙️ AI33 / OpenSpeaker":
    with st.sidebar:
        jobs = st.session_state.get("background_jobs", {})
        workspaces = st.session_state.get("workspaces", {})
        if isinstance(jobs, dict) and jobs:
            st.markdown("**⏳ Tiến độ YouTube Translator**")
            for session_id, job in list(jobs.items()):
                if not isinstance(job, dict):
                    continue
                try:
                    pct, stage = job["progress"].snapshot()
                    done = job["future"].done()
                except (KeyError, AttributeError, TypeError):
                    continue
                name = workspaces.get(session_id, {}).get("name", "Phiên dịch")
                if done:
                    st.success(f"✅ {name}: hoàn tất. Về App 1 để nhận kết quả.")
                else:
                    st.progress(pct, text=f"{name}: {stage}")
    st.subheader("🎙️ App 2 — AI33 / OpenSpeaker")
    st.info(
        "AI33 là website độc lập. Nếu website không cho nhúng hoặc đăng nhập "
        "trong iframe bị chặn, hãy sử dụng nút mở AI33 bên dưới."
    )
    # Do not transfer any translator settings, keys or session data to AI33.
    components.iframe("https://ai33.pro/app", height=920, scrolling=True)
    st.link_button(
        "↗ Mở AI33 trực tiếp nếu khung không hoạt động",
        "https://ai33.pro/app",
        use_container_width=True,
    )
    st.caption(
        "Tác vụ hồ sơ nhân vật tiếp tục khi chuyển mục hoặc tải lại trang, "
        "miễn là máy chủ vẫn hoạt động. "
        "Tác vụ của AI33 do AI33 quản lý riêng."
    )
    _save_cloud_state()
    _save_browser_api_settings()
    _save_browser_sessions()
    st.stop()

with st.sidebar:
    sid = st.session_state.selected_session
    if sid not in st.session_state.workspaces:
        sid = next(iter(st.session_state.workspaces))
        st.session_state.selected_session = sid
    session = st.session_state.workspaces[sid]

    st.header("📁 Quản lý phiên làm việc")
    # Style saved-session status buttons and New Session; no individual
    # deletion controls are rendered, so no red Xóa buttons can be truncated.
    st.markdown(
        """
        <style>
        /* New session: always green. */
        [data-testid="stSidebar"] .st-key-create_new_session button {
            color: #ffffff !important;
            background: #16803e !important;
            border: 1px solid #166534 !important;
            font-weight: 800 !important;
            box-shadow: 0 2px 0 #14532d, 0 3px 7px rgba(0, 0, 0, .15);
        }
        [data-testid="stSidebar"] .st-key-create_new_session button:hover {
            background: #1b994e !important;
        }

        /* Finished: green. Pending/running/failed/interrupted: red.
           Selection is shown by a green checkmark, not a yellow box. */
        [data-testid="stSidebar"] [class*="st-key-session_status_completed_"] button {
            color: #ffffff !important;
            background: #16803e !important;
            border: 1px solid #166534 !important;
            font-weight: 750 !important;
        }
        [data-testid="stSidebar"] [class*="st-key-session_status_completed_"] button:hover {
            background: #1b994e !important;
        }
        [data-testid="stSidebar"] [class*="st-key-session_status_pending_"] button {
            color: #ffffff !important;
            background: #c62828 !important;
            border: 1px solid #991b1b !important;
            font-weight: 750 !important;
        }
        [data-testid="stSidebar"] [class*="st-key-session_status_pending_"] button:hover {
            background: #dc3636 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if st.button("➕ Tạo phiên mới", key="create_new_session", use_container_width=True):
        old_name = session["name"]
        still_running = (
            sid in st.session_state.background_jobs
            and not st.session_state.background_jobs[sid]["future"].done()
        )
        was_archived = archive_previous_session(sid)
        newid = uuid.uuid4().hex
        st.session_state.saved_session_order += 1
        new_session = blank_session(unique_name(f"Phiên {st.session_state.saved_session_order}"))
        new_session["saved_order"] = st.session_state.saved_session_order
        st.session_state.workspaces[newid] = new_session
        st.session_state["_open_session_next"] = newid
        if still_running:
            st.session_state["_session_flash"] = (
                f"⏳ Phiên '{old_name}' vẫn đang chạy nền. "
                "Bạn có thể làm video mới; kết quả sẽ tự được lưu khi hoàn thành."
            )
        elif was_archived:
            st.session_state["_session_flash"] = (
                f"✅ Đã lưu phiên '{old_name}' trong Danh sách phiên đã chạy. "
                "Bạn có thể nhấn trực tiếp vào tên phiên để xem lại."
            )
        else:
            st.session_state["_session_flash"] = (
                "➕ Đã tạo phiên mới. Phiên trước chưa có kết quả xử lý nên không lưu vào danh sách."
            )
        _persist_and_rerun()

    if st.session_state.pop("_reset_delete_confirm_next", False):
        st.session_state["confirm_delete_all_sessions"] = False
    confirm_all = st.checkbox(
        "Tôi xác nhận xóa tất cả phiên và dữ liệu",
        key="confirm_delete_all_sessions",
    )
    if st.button(
        "🗑️ Xóa tất cả phiên đã lưu",
        type="secondary",
        key="delete_all_sessions",
        disabled=not confirm_all,
        use_container_width=True,
    ):
        new_id = uuid.uuid4().hex
        new_session = blank_session("Phiên 1")
        new_session["saved_order"] = 1
        st.session_state.saved_session_order = 1
        # Cancel queued jobs; running requests may finish but their results are discarded.
        for old_session_id, old_session in st.session_state.workspaces.items():
            IMAGE_STORE.clear(_job_scope(), old_session_id)
            get_job_registry().cancel(
                profile_job(old_session).get("run_id"), old_session_id,
                "characters:" + _job_scope(),
            )
            get_job_registry().cancel(
                old_session.get("job_run_id"), old_session_id, _job_scope()
            )
        for job in st.session_state.background_jobs.values():
            job["progress"].cancel()
            job["future"].cancel()
        for old_session_id in list(st.session_state.workspaces):
            _clear_session_widgets(old_session_id)
        st.session_state.background_jobs = {}
        st.session_state.profile_background_jobs = {}
        st.session_state.workspaces = {new_id: new_session}
        st.session_state["_browser_delete_revision"] = uuid.uuid4().hex
        st.session_state.pop("_browser_delete_confirmed", None)
        st.session_state["confirm_delete_session_id"] = None
        st.session_state["_session_flash"] = (
            "🗑️ Đã xóa toàn bộ danh sách phiên và dữ liệu liên quan. "
            "Các kết quả cũ không còn trong app hoặc bản lưu hiện tại."
        )
        st.session_state["editing_session_id"] = None
        st.session_state["_open_session_next"] = new_id
        st.session_state["_reset_delete_confirm_next"] = True
        _persist_and_rerun()

    st.divider()
    st.markdown("**📚 Danh sách phiên đã chạy**")
    st.caption(
        "Nhấp tên phiên để mở · nhấp đúp để đổi tên ngay tại ô (Enter để lưu). "
        "🟢 Hoàn thành · 🔴 Chưa xong/lỗi · ✅ Đang xem có dấu tích xanh."
    )
    name_message = st.session_state.pop("session_name_message", None)
    if name_message:
        st.warning(name_message)

    saved_sessions = sorted(
        (
            (saved_id, saved_record)
            for saved_id, saved_record in st.session_state.workspaces.items()
            if saved_record.get("processed", False)
            or saved_record.get("job_state") in ("running", "completed", "failed", "interrupted")
            or saved_id in st.session_state.background_jobs
        ),
        key=lambda pair: pair[1].get("saved_order", 0),
        reverse=True,
    )
    if not saved_sessions:
        st.caption("Chưa có phiên nào được bắt đầu. Bấm BẮT ĐẦU TẠO TOÀN BỘ trước khi tạo phiên mới.")
    for saved_id, saved_record in saved_sessions:
        with st.container():
            job = st.session_state.background_jobs.get(saved_id)
            currently_running = bool(job and not job["future"].done())
            if currently_running:
                pct, _ = job["progress"].snapshot()
                status_suffix = f" ⏳ {pct}%"
            elif saved_record.get("job_state") in ("failed", "interrupted"):
                status_suffix = " ⚠️"
            elif saved_record.get("job_state") == "running":
                status_suffix = " ⏳"
            else:
                # Finished sessions are green by color only, without a checkmark.
                status_suffix = ""
            # Completion color is independent of the session being viewed.
            # The selected session has a small green check inside its name.
            is_selected = saved_id == sid
            session_tone = (
                "completed"
                if saved_record.get("job_state") == "completed" and not currently_running
                else "pending"
            )
            with st.container(key=f"session_status_{session_tone}_{saved_id}"):
                if streamlit_runtime_exists() and not st.session_state.get("_session_name_test_fallback", False):
                    # Native Streamlit buttons have no double-click event.
                    # A small browser component distinguishes one click (open)
                    # from two clicks (edit name directly inside the same box).
                    event = session_name_control(
                        saved_record["name"], status_suffix, session_tone,
                        selected=is_selected,
                        key=f"session_name_control_{saved_id}",
                    )
                    if isinstance(event, dict) and isinstance(event.get("seq"), str):
                        seen = st.session_state.setdefault("_session_name_events_seen", {})
                        if event["seq"] != seen.get(saved_id):
                            seen[saved_id] = event["seq"]
                            action = event.get("action")
                            if action == "open" and saved_id != sid:
                                sync_form(sid)
                                st.session_state["_open_session_next"] = saved_id
                                _persist_and_rerun()
                            elif action == "rename":
                                try:
                                    new_name = rename_record(
                                        st.session_state.workspaces, saved_id,
                                        event.get("name"),
                                    )
                                except ValueError as exc:
                                    st.session_state["session_name_message"] = str(exc)
                                    st.rerun()
                                else:
                                    st.session_state["_session_flash"] = (
                                        f"✅ Đã đổi tên phiên thành '{new_name}'."
                                    )
                                    _persist_and_rerun()
                else:
                    # Streamlit AppTest has no JavaScript/browser; retain the
                    # one-click selection control for automated smoke tests.
                    label = f"📄 {saved_record['name']}{status_suffix}"
                    if is_selected:
                        label += " ✅"
                    if st.button(
                        label,
                        key=f"open_saved_session_{saved_id}",
                        use_container_width=True,
                        type="primary" if saved_id == sid else "secondary",
                    ):
                        if saved_id != sid:
                            sync_form(sid)
                            st.session_state["_open_session_next"] = saved_id
                            _persist_and_rerun()
        if st.button(
            "Xóa", key=f"delete_session_{saved_id}",
            use_container_width=True, type="secondary",
        ):
            st.session_state["confirm_delete_session_id"] = saved_id
            st.rerun()
        if st.session_state.get("confirm_delete_session_id") == saved_id:
            st.warning(
                f"Bạn chắc chắn muốn xóa phiên '{saved_record['name']}'? "
                "Nội dung, bản dịch và form video của phiên sẽ bị xóa."
            )
            confirm_col, cancel_col = st.columns(2, gap="small")
            with confirm_col:
                if st.button(
                    "✅ Xác nhận xóa", key=f"confirm_delete_{saved_id}",
                    use_container_width=True,
                ):
                    delete_saved_session(saved_id)
                    _persist_and_rerun()
            with cancel_col:
                if st.button(
                    "Hủy", key=f"cancel_delete_{saved_id}",
                    use_container_width=True,
                ):
                    st.session_state["confirm_delete_session_id"] = None
                    st.rerun()
    # Session content still auto-saves on every rerun via Supabase or
    # local browser storage. Only the optional backup/import UI is removed.
    # Keep cloud logout accessible outside the retired backup section.
    if CLOUD_ENABLED:
        st.divider()
        if st.button("🚪 Đăng xuất", key="cloud_logout", use_container_width=True):
            try:
                _save_cloud_state(force=True)
            except Exception as exc:
                st.error(f"Chưa thể lưu trước khi đăng xuất: {exc}")
            else:
                for old_sid, old_record in st.session_state.workspaces.items():
                    IMAGE_STORE.clear(_job_scope(), old_sid)
                    get_job_registry().cancel(
                        old_record.get("job_run_id"), old_sid, _job_scope()
                    )
                for job in st.session_state.background_jobs.values():
                    job["progress"].cancel()
                    job["future"].cancel()
                st.session_state.clear()
                st.rerun()

    st.divider()
    with st.expander("📥 Phụ đề YouTube dự phòng", expanded=False):
        st.caption(
            "Mặc định thử lấy phụ đề trực tiếp. Nếu YouTube chặn IP Cloud, "
            "app sẽ tự thử dịch vụ Supadata khi bạn nhập key bên dưới."
        )
        try:
            backup_key_secret = str(st.secrets.get("SUPADATA_API_KEY", "") or "")
        except Exception:
            backup_key_secret = ""
        transcript_api_key_entered = st.text_input(
            "Supadata API key (khác API dịch)",
            type="password",
            key="supadata_api_key_input",
            placeholder="Nhập key nếu YouTube chặn trích xuất",
        )
        transcript_api_key = transcript_api_key_entered.strip() or backup_key_secret.strip()
        st.markdown("[🔗 Lấy API key phụ đề Supadata](https://supadata.ai/)")
        st.caption("Dịch vụ phụ đề có giới hạn lượt và có thể tính phí. Không bắt buộc nếu bạn dùng file phụ đề.")
        st.caption("🔒 API key sẽ tự lưu mã hóa theo tài khoản (Supabase) hoặc trên trình duyệt này nếu không dùng Supabase.")

    st.divider()
    with st.expander("🖼️ API tạo ảnh nhân vật", expanded=False):
        st.caption(
            "Tự tạo ảnh ngay khi xong hồ sơ nhân vật. Cần OpenAI Images API "
            "(khác API dịch Groq/Gemini). Có thể phát sinh phí theo số nhân vật."
        )
        image_api_key_entered = st.text_input(
            "🔐 OpenAI Images API key", type="password",
            key="image_api_key_input",
        )
        try:
            image_key_secret = str(st.secrets.get("OPENAI_IMAGE_API_KEY", "") or "")
        except (FileNotFoundError, OSError):
            image_key_secret = ""
        image_api_key = image_api_key_entered.strip() or image_key_secret.strip()
        if not image_api_key:
            st.caption("Chưa có API ảnh: app vẫn tạo bản dịch, SEO và form video; chưa thể tạo PNG.")
        st.caption(f"Model ảnh mặc định: {IMAGE_MODEL}. Tối đa 8 nhân vật/phiên.")
        st.caption(
            "🔎 Lỗi HTTP 401 nghĩa là API tạo ảnh không xác thực được key. "
            "Key ảnh phải là OpenAI API key riêng, không dùng key dịch văn bản."
        )
        st.markdown("[🔑 Tạo/kiểm tra OpenAI API key](https://platform.openai.com/api-keys)")

    st.divider()
    with st.expander("🔑 Cấu hình API đa nền tảng", expanded=False):
        st.caption("Groq • Gemini • OpenAI • Claude • Claude Gateway • API bên thứ ba • OpenRouter • DeepSeek • Together AI")
        pending_provider = st.session_state.pop("_pending_api_provider", None)
        if pending_provider in PROVIDERS:
            st.session_state["api_provider"] = pending_provider
        provider = st.selectbox(
            "CHỌN NỀN TẢNG AI",
            list(PROVIDERS),
            key="api_provider",
        )
        preset = PROVIDERS[provider]
        provider_id = provider
        # Rehydrate keys and model IDs when changing back to a provider:
        # Streamlit automatically prunes inactive input widget state.
        activate_provider_settings(st.session_state, provider)
        secret_name = preset["secret"]
        # Apply profile changes before instantiating Streamlit input widgets.
        pending_free = st.session_state.pop("_pending_free_provider", None)
        if pending_free == provider and provider in ("Groq", "Google Gemini"):
            st.session_state[f"api_model_id_{provider}"] = preset["model"]
            st.session_state[f"api_base_{provider}"] = preset["base_url"]
        try:
            stored_key = str(st.secrets.get(secret_name, "") or "") if secret_name else ""
        except Exception:
            stored_key = ""
        entered_key = st.text_input(
            ("🔐 Gateway AUTH_TOKEN" if provider == "Claude Gateway (AUTH_TOKEN)"
             else "🔐 Claude API Key" if provider == "Claude (Anthropic)" else "🔐 API Key"),
            key=f"api_key_{provider_id}",
            type="password",
            placeholder=("Token mới từ gateway" if provider == "Claude Gateway (AUTH_TOKEN)"
                         else "sk-ant-..." if provider == "Claude (Anthropic)" else
                         "Nhập API key riêng của nền tảng đã chọn"),
        )
        key = entered_key.strip() or stored_key.strip()

        base_url = st.text_input(
            "🌐 Base URL",
            value=preset["base_url"],
            key=f"api_base_{provider_id}",
            placeholder="https://your-provider.com/v1",
        ).strip()

        model_widget_key = f"api_model_id_{provider_id}"
        pending = st.session_state.pop(f"pending_model_{provider_id}", None)
        if pending:
            st.session_state[model_widget_key] = pending
        model = st.text_input(
            "🤖 Model ID",
            value=preset["model"],
            key=model_widget_key,
            placeholder=("Ví dụ: claude-sonnet-4-6" if provider == "Claude (Anthropic)"
                         else "Ví dụ: openai/gpt-oss-120b"),
        ).strip()

        # Keep original third-party protocols and provider-specific actions
        # without crowding the three fundamental API inputs above.
        with st.popover("⚙️ Hướng dẫn và tùy chọn nâng cao", use_container_width=True):
            if provider == "Groq":
                st.caption(
                    "🟡 GroqCloud (khác Grok của xAI). Gói miễn phí có giới hạn "
                    "token/phút và số yêu cầu/ngày. Model gợi ý: "
                    "openai/gpt-oss-20b; không bảo đảm chạy video dài mà không chờ."
                )
                st.markdown(
                    "[Xem hạn mức Groq](https://console.groq.com/settings/limits)"
                )
            elif provider == "Google Gemini":
                st.info(
                    "💠 Gemini dùng API Google chính thức (generateContent), "
                    "xác thực x-goog-api-key. Model Flash-Lite tiết kiệm, "
                    "thích hợp thử nghiệm gói miễn phí. "
                    "Gói miễn phí vẫn giới hạn lượt gọi."
                )
                st.markdown(
                    "[Lấy Gemini API key tại Google AI Studio]"
                    "(https://aistudio.google.com/apikey) "
                    "· [Kiểm tra hạn mức](https://aistudio.google.com/usage)"
                )
            api_format = None
            api_auth_mode = None
            if provider == "API bên thứ ba (tùy chỉnh)":
                st.info(
                    "🌐 Tự nhập API Key, Base URL và Model ID của dịch vụ bên thứ ba. "
                    "Chọn đúng chuẩn API và kiểu xác thực mà nhà cung cấp hướng dẫn."
                )
                format_label = st.selectbox(
                    "📡 Chuẩn API",
                    ["OpenAI Chat Completions", "Anthropic Messages"],
                    key=f"api_format_{provider_id}",
                )
                auth_label = st.selectbox(
                    "🔏 Kiểu xác thực",
                    ["Bearer Token", "x-api-key"],
                    key=f"api_auth_mode_{provider_id}",
                )
                api_format = {
                    "OpenAI Chat Completions": "chat",
                    "Anthropic Messages": "anthropic",
                }[format_label]
                api_auth_mode = {
                    "Bearer Token": "bearer", "x-api-key": "api_key",
                }[auth_label]
                st.caption(
                    "Ví dụ OpenAI-compatible: https://provider.example/v1. "
                    "Với Anthropic Messages, có thể dùng domain gốc "
                    "(app tự thêm /v1) hoặc Base URL đã có đường dẫn API. "
                    "Không thêm /chat/completions hay /messages vào Base URL."
                )
                st.warning(
                    "Chỉ kết nối dịch vụ HTTPS đáng tin cậy: API key và nội dung "
                    "video được gửi tới máy chủ bên thứ ba. "
                    "Quét model có thể không được hỗ trợ; có thể nhập Model ID thủ công."
                )
            if provider == "Claude Gateway (AUTH_TOKEN)":
                st.info(
                    "🔑 Dành cho dịch vụ gateway dùng ANTHROPIC_BASE_URL và "
                    "ANTHROPIC_AUTH_TOKEN trong Claude Code. Đây không phải API "
                    "Anthropic chính thức. Chỉ sử dụng máy chủ bạn tin tưởng vì "
                    "nội dung và token sẽ được gửi tới địa chỉ đó."
                )
                st.caption(
                    "Base URL: dùng ANTHROPIC_BASE_URL trong cấu hình Claude Code; "
                    "app sẽ thêm /v1/messages khi bạn nhập domain gốc. "
                    "Token: dùng token MỚI thay cho ANTHROPIC_AUTH_TOKEN đã lộ. "
                    "Model ID phải là model gateway thực sự hỗ trợ."
                )
            if provider == "Claude (Anthropic)":
                st.info(
                    "🟣 Claude API chính thức: nhập API key từ Anthropic Console. "
                    "Ứng dụng tự dùng Messages API, không cần Base URL tùy chỉnh."
                )
                st.markdown(
                    "[🔗 Lấy Claude API key tại Anthropic Console]"
                    "(https://platform.claude.com/settings/keys)"
                )
            # A Claude Code gateway token uses Authorization: Bearer. The
            # official Claude provider uses an Anthropic API-key header.
            # Warn before sending credentials to the wrong kind of endpoint.
            if (
                provider == "Claude (Anthropic)"
                and base_url.rstrip("/") != "https://api.anthropic.com/v1"
            ):
                st.warning(
                    "⚠️ Bạn đang chọn Claude API chính thức nhưng Base URL lại "
                    "là máy chủ tùy chỉnh. Nếu đây là ANTHROPIC_BASE_URL trong "
                    "Claude Code, hãy chuyển sang Claude Gateway (AUTH_TOKEN); "
                    "cách gửi token của hai lựa chọn khác nhau."
                )
                if st.button(
                    "🔁 Chuyển sang Claude Gateway",
                    key="switch_to_claude_gateway",
                    use_container_width=True,
                ):
                    gateway = "Claude Gateway (AUTH_TOKEN)"
                    if not st.session_state.get(f"api_base_{gateway}"):
                        st.session_state[f"api_base_{gateway}"] = base_url
                    # Do not copy possibly exposed/revoked credentials across modes.
                    # A fresh gateway token must be entered explicitly.
                    st.session_state["_pending_api_provider"] = gateway
                    _persist_and_rerun()
            if provider == "Claude Gateway (AUTH_TOKEN)":
                st.caption(
                    "ℹ️ Nhiều gateway chỉ hỗ trợ /v1/messages, không hỗ trợ "
                    "/v1/models. Quét model thất bại không đồng nghĩa với "
                    "không thể dịch. Nhập Model ID đúng rồi nhấn "
                    "'Kiểm tra kết nối API'."
                )

            if provider in ("Groq", "Google Gemini"):
                if st.button(
                    "⚡ Áp dụng cấu hình phù hợp gói miễn phí",
                    key=f"free_profile_{provider}",
                    use_container_width=True,
                ):
                    st.session_state["_pending_free_provider"] = provider
                    _persist_and_rerun()

        if st.button("🔎 Quét Model từ API", use_container_width=True, key=f"scan_{provider_id}"):
            try:
                with st.spinner("Đang lấy danh sách Model..."):
                    if provider == "API bên thứ ba (tùy chỉnh)":
                        available = list_models(
                            provider, base_url, key,
                            api_format=api_format, auth_mode=api_auth_mode,
                        )
                    else:
                        available = list_models(provider, base_url, key)
                st.session_state[f"models_found_{provider_id}"] = available
                if not available:
                    st.warning("API không trả về danh sách Model. Bạn vẫn có thể nhập Model ID thủ công.")
            except Exception as exc:
                st.error(str(exc))

        discovered = st.session_state.get(f"models_found_{provider_id}", [])
        if discovered:
            scan_choice = st.selectbox(
                f"Model khả dụng ({len(discovered)})",
                discovered,
                key=f"model_picker_{provider_id}",
            )
            if st.button("📌 Dùng Model đã chọn", key=f"set_model_{provider_id}", use_container_width=True):
                st.session_state[f"pending_model_{provider_id}"] = scan_choice
                _persist_and_rerun()

        if key:
            st.caption("✅ Đã nhập API key" + (" (Secrets)" if not entered_key else ""))
        else:
            st.caption("⚠️ Chưa nhập API key.")
        st.caption(
            "Các API tương thích OpenAI dùng endpoint /chat/completions; "
            "Claude dùng /messages. Chỉ nhập Base URL HTTPS công khai, đáng tin cậy."
        )
        test_api = st.button("🧪 Kiểm tra kết nối API", use_container_width=True)
        st.caption("API key không được ghi vào GitHub hoặc dữ liệu phiên. Dịch vụ API có thể tính phí.")
        st.caption("💾 Cấu hình từng nhà cung cấp được tự lưu và khôi phục khi mở lại app; có thể thay đổi bất cứ lúc nào.")


def ai(prompt):
    """Use the selected provider and recover from temporary gateway failures."""
    options = {}
    if provider == "API bên thứ ba (tùy chỉnh)":
        options = {"api_format": api_format, "auth_mode": api_auth_mode}
    retry_notice = None

    def report_retry(message):
        nonlocal retry_notice
        if retry_notice is None:
            retry_notice = st.empty()
        retry_notice.info(message)

    try:
        return retry_transient_provider(lambda: generate_text(
            provider, base_url, model, key, prompt,
            **options,
        ), report=report_retry)
    finally:
        if retry_notice is not None:
            retry_notice.empty()


def fetch_best_transcript(video_id):
    """Retrieve a real available subtitle track, including auto-generated captions."""
    tracks = list(YouTubeTranscriptApi().list(video_id))
    if not tracks:
        raise ValueError("Video không có phụ đề để trích xuất.")
    preferred = {"vi": 0, "en": 1, "pl": 2}
    tracks.sort(key=lambda t: (bool(t.is_generated), preferred.get(t.language_code, 10)))
    for track in tracks:
        try:
            segments = track.fetch()
            content = " ".join(
                str(segment.text).strip()
                for segment in segments if getattr(segment, "text", "").strip()
            ).strip()
            if content:
                return content, track.language
        except Exception:
            continue
    raise ValueError("Không đọc được phụ đề. Video có thể đang bị YouTube hạn chế.")


def split_script(text, size=5500):
    """Keep every character, splitting near a sentence/space when possible."""
    pieces = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            split_at = max(text.rfind("\n", start + size // 2, end),
                           text.rfind(". ", start + size // 2, end))
            if split_at > start:
                end = split_at + 1
        pieces.append(text[start:end])
        start = end
    return pieces


def translate_full_script(source_text, target_language, report=None):
    if not source_text.strip():
        raise ValueError("Không có phụ đề hoặc văn bản đầu vào.")
    if len(source_text) > 350000:
        raise ValueError("Văn bản quá dài (trên 350.000 ký tự). Hãy chia thành nhiều video.")
    pieces = split_script(source_text)
    translated_parts = []
    for idx, part in enumerate(pieces, start=1):
        if report:
            report(idx, len(pieces))
        translated_parts.append(translate_part_faithfully(
            part, target_language, ai,
            before=pieces[idx - 2][-800:] if idx > 1 else "",
            after=pieces[idx][:800] if idx < len(pieces) else "",
            previous=translated_parts[-1] if translated_parts else "",
        ))
    return "\n\n".join(translated_parts)


def story_overview(text):
    """Represent the WHOLE long story for generation instead of truncating its ending."""
    if len(text) <= 24000:
        return text
    blocks = split_script(text, 15000)
    summaries = []
    for index, part in enumerate(blocks, start=1):
        summaries.append(ai(
            "Summarize the specific characters, locations, chronological events and "
            "visual details of this part in 180-280 words. Do not invent facts. "
            f"Part {index}/{len(blocks)}:\n" + part
        ))
    return "\n".join(f"Phần {i}: {part}" for i, part in enumerate(summaries, 1))


def load_json_answer(raw, expected):
    left, right = raw.find("{"), raw.rfind("}")
    if left < 0 or right < left:
        raise ValueError("AI không trả về JSON đúng định dạng; hãy chạy lại mục này.")
    try:
        obj = json.loads(raw[left:right + 1])
    except (ValueError, TypeError) as exc:
        raise ValueError("AI trả JSON chưa hợp lệ. Hãy thử tạo lại mục này.") from exc
    if not isinstance(obj, dict) or expected not in obj:
        raise ValueError("Kết quả AI thiếu dữ liệu cần thiết; hãy thử lại.")
    return obj


def create_target_metadata(script, original_title, original_description, target_language):
    brief = story_overview(script)
    result = ai(
        f"Soạn nội dung YouTube chính xác và tự nhiên hoàn toàn bằng {target_language}. "
        "Tiêu đề: nếu có tiêu đề gốc hãy dịch sát và diễn đạt hấp dẫn, không thêm tình tiết. "
        "Mô tả: giữ đúng nhân vật, sự kiện, không bịa; dùng icon/emoji phù hợp vừa phải. "
        "SEO: tạo 15 từ khóa thật liên quan bằng ngôn ngữ đích. "
        'Chỉ trả JSON: {"title":"...", "description":"...", "tags":["...", "..."]}, '
        "không markdown.\n"
        f"Tiêu đề gốc: {original_title}\nMô tả gốc: {original_description}\n"
        f"Nội dung video:\n{brief}"
    )
    data = load_json_answer(result, "title")
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    tags = data.get("tags", [])
    tags = ", ".join(str(item).strip() for item in tags) if isinstance(tags, list) else str(tags).strip()
    if not title or not description or not tags:
        raise ValueError("AI trả về thiếu tiêu đề, mô tả hoặc từ khóa SEO.")
    return title, description, tags


if test_api:
    try:
        with st.sidebar:
            with st.spinner("Đang kiểm tra Base URL, API Key và Model..."):
                answer = ai("Hãy trả lời duy nhất từ OK.")
            st.success(f"✅ Kết nối {provider} thành công với Model {model}.")
    except TransientProviderError as exc:
        st.sidebar.warning(
            f"⚠️ Máy chủ API/Gateway đang gặp lỗi HTTP {exc.status_code}. "
            "Đây có thể là sự cố của gateway hoặc dịch vụ phía sau, "
            "không khẳng định API key hay model sai. "
            "Bạn có thể thử lại sau; nếu kéo dài, liên hệ đơn vị cấp gateway "
            "hoặc chuyển sang API khác. "
            "App sẽ tự thử lại có giới hạn khi chạy dịch toàn bộ."
        )
    except Exception as exc:
        st.sidebar.error(str(exc))


def output(title, text, *, allow_download=False):
    st.markdown("**" + title + "**")
    if not text:
        st.caption("Chưa có nội dung.")
        return
    # Every section keeps its built-in Copy icon; .txt download is restricted
    # to the complete translation section.
    st.code(text, language=None, wrap_lines=True)
    if allow_download:
        st.download_button(
            "⬇️ Tải nội dung (.txt)", text, file_name="ban-dich-hoan-chinh.txt",
            mime="text/plain", key=f"save_{sid}_translated"
        )


flash = st.session_state.pop("_session_flash", None)
if flash:
    st.success(flash)
st.info(f"📂 **Phiên đang mở:** {session['name']} — mọi kết quả chỉ thuộc phiên này.")
if DURABLE_QUEUE_ENABLED:
    st.caption(
        "🖥️ Hàng đợi bền vững: worker độc lập xử lý và tự lưu lên Supabase "
        "ngay cả khi Streamlit Cloud ngủ."
    )
elif CLOUD_ENABLED:
    st.caption(
        "ℹ️ Chưa bật worker độc lập: tác vụ Streamlit có thể dừng nếu "
        "chính máy chủ bị tạm ngưng hoặc khởi động lại."
    )
if session.get("job_state") == "running":
    st.info(
        f"⏳ Phiên này đang xử lý: {session.get('job_stage', 'Đang chạy')} "
        f"({session.get('job_percent', 0)}%). "
        "Bạn có thể tạo phiên mới; tác vụ hiện tại không bị dừng."
    )
elif session.get("job_state") in ("failed", "interrupted"):
    st.error(f"⚠️ Phiên này chưa hoàn tất: {session.get('job_error', 'Không rõ lỗi')}")
    st.caption("Các kết quả đã tạo vẫn được giữ trong phiên. Có thể dùng nút BẮT ĐẦU TẠO TOÀN BỘ để thử lại.")
session["url"] = st.text_input(
    "🔗 Dán link video YouTube",
    value=session["url"], key=f"field_{sid}_url",
)
match = re.search(r"(?:v=|youtu\.be/|/shorts/|/live/)([\w-]{11})", session["url"])
vid = match.group(1) if match else None

with st.expander("📄 Phụ đề dự phòng từ máy (.srt / .vtt / .txt)", expanded=False):
    uploaded_subtitle = st.file_uploader(
        "Tải phụ đề khi YouTube chặn máy chủ",
        type=["txt", "srt", "vtt"],
        key=f"subtitle_fallback_upload_{sid}",
    )
    if uploaded_subtitle is not None:
        st.caption("✅ Đã chọn file. Khi bắt đầu, app sẽ ưu tiên file này và không gọi phụ đề YouTube.")
    else:
        st.caption("Có thể để trống nếu dùng YouTube trực tiếp hoặc dịch vụ phụ đề Supadata.")

# Target language is chosen next to the generation controls, not the sidebar.
lang_value = session.get("language", "Tiếng Ba Lan")
language = st.selectbox(
    "🌍 Ngôn ngữ đích",
    LANGUAGES,
    index=LANGUAGES.index(lang_value) if lang_value in LANGUAGES else 0,
    key=f"field_{sid}_language",
)
session["language"] = language

if st.button("🚀 BẮT ĐẦU TẠO TOÀN BỘ", type="primary",
             use_container_width=True, key=f"run_all_{sid}"):
    sync_form(sid)
    if not key.strip():
        st.error("Hãy nhập API key trước khi chạy.")
    elif not vid and uploaded_subtitle is None and not session["source"].strip():
        st.warning("Hãy dán link YouTube hoặc tải file phụ đề (.srt/.vtt/.txt).")
    elif (
        sid in st.session_state.background_jobs
        and not st.session_state.background_jobs[sid]["future"].done()
    ):
        st.info("Phiên này đang chạy nền. Bạn có thể bấm Tạo phiên mới ngay.")
    elif DURABLE_QUEUE_ENABLED and session.get("job_state") == "running" and session.get("job_queue_id"):
        st.info("Phiên này đã ở hàng đợi bền vững; đang chờ hoặc đang được worker xử lý.")
    elif not DURABLE_QUEUE_ENABLED and sum(
        not job["future"].done()
        for job in st.session_state.background_jobs.values()
    ) >= 3:
        st.warning("Tối đa 3 phiên được xử lý đồng thời. Hãy chờ một phiên hoàn tất.")
    else:
        try:
            validate_base_url(base_url)
            if not model.strip():
                raise ValueError("Hãy nhập Model ID.")
            progress = JobProgress()
            run_id = uuid.uuid4().hex
            subtitle_from_file = (
                parse_uploaded_subtitles(uploaded_subtitle.name, uploaded_subtitle.getvalue())
                if uploaded_subtitle is not None else ""
            )
            snapshot = {
                "url": session["url"],
                "source": session.get("source", ""),
                "uploaded_source": subtitle_from_file,
                "supadata_key": transcript_api_key,
                "title": session.get("title", ""),
                "description": session.get("description", ""),
                "language": language,
                "provider": provider,
                "base_url": base_url,
                "model": model,
                "api_key": key,
                "auto_video_forms": False,  # Generate ONLY after audio upload + user action.
                "video_style": "Điện ảnh chân thực",
                "auto_character_images": bool(image_api_key),
                "image_api_key": image_api_key,
                "image_model": IMAGE_MODEL,
                "image_scope": _job_scope(),
                "image_session_id": sid,
            }
            if provider == "API bên thứ ba (tùy chỉnh)":
                snapshot["api_format"] = api_format
                snapshot["auth_mode"] = api_auth_mode
            if DURABLE_QUEUE_ENABLED:
                ensure_durable_worker_available()
                # Save selected session AND current encrypted API settings first.
                _save_cloud_state(force=True)
                queue_snapshot = {
                    item: value for item, value in snapshot.items()
                    if item not in ("api_key", "supadata_key", "image_api_key")
                }
                queued = submit_job(
                    st.secrets, _refresh_login(), sid, "full", queue_snapshot,
                    {"api_key": key, "supadata_key": transcript_api_key,
                     "image_api_key": image_api_key},
                )
                session["job_queue_id"] = queued
                session["job_state"] = "running"
                session["job_percent"] = 0
                session["job_stage"] = "Đã giao việc cho worker độc lập"
                session["job_run_id"] = ""
                session["job_error"] = ""
                session["saved"] = True
                session["processed"] = True
                st.session_state["_session_flash"] = (
                    "✅ Phiên đã vào hàng đợi bền vững. "
                    "Bạn có thể ngủ; worker độc lập sẽ xử lý và tự lưu."
                )
                _persist_and_rerun()
                st.stop()
            # Worker keeps its own authenticated checkpoint configuration.
            # Never persist provider keys inside a session record.
            snapshot["sid"] = sid
            snapshot["run_id"] = run_id
            snapshot["cloud"] = None
            if CLOUD_ENABLED:
                auth = _refresh_login()
                snapshot["cloud"] = {
                    "auth": dict(auth),
                    "secrets": {
                        name: str(st.secrets[name])
                        for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY",
                                     "SESSION_ENCRYPTION_KEY")
                    },
                }
            session["job_state"] = "running"
            session["job_percent"] = 0
            session["job_stage"] = "Đã xếp tác vụ vào hàng đợi"
            session["job_error"] = ""
            session["job_run_id"] = run_id
            session["saved"] = True
            # Commit run identity to cloud BEFORE the worker starts.
            _save_cloud_state(force=True)
            job_future = get_job_executor().submit(
                run_full_job_with_server_saves, snapshot, progress
            )
            st.session_state.background_jobs[sid] = {
                "future": job_future,
                "progress": progress,
                "run_id": run_id,
            }
            get_job_registry().register(
                run_id, sid, _job_scope(), job_future, progress
            )
            st.session_state["_session_flash"] = (
                f"⏳ Phiên '{session['name']}' đã chạy nền. "
                "Bạn có thể nhấn Tạo phiên mới, phiên này vẫn tiếp tục."
            )
            _persist_and_rerun()
        except Exception as exc:
            st.error(f"Không thể khởi động tác vụ: {exc}")


@st.fragment(run_every="3s")
def show_background_job_progress():
    """Poll in the Streamlit thread; worker threads never call st.*."""
    main_changed = collect_completed_jobs()
    video_changed = collect_video_background_jobs()
    profile_changed = collect_profile_background_jobs()
    profile_changed = st.session_state.pop("_profile_ui_refresh_pending", False) or profile_changed
    durable_changed = sync_durable_queue()
    if main_changed or video_changed or profile_changed or durable_changed:
        _persist_and_rerun()
    for session_id, job in list(st.session_state.background_jobs.items()):
        if session_id not in st.session_state.workspaces:
            continue
        percent, stage = job["progress"].snapshot()
        name = st.session_state.workspaces[session_id]["name"]
        st.progress(percent, text=f"{name}: {stage}")
    active_queue = [
        (item.get("name","Phiên"), item.get("job_percent",0),
         item.get("job_stage","Đang chờ worker"))
        for item in st.session_state.workspaces.values()
        if DURABLE_QUEUE_ENABLED and item.get("job_queue_id")
           and item.get("job_state") == "running"
    ]
    for name, pct, stage in active_queue:
        st.progress(int(pct or 0), text=f"{name}: {stage}")
    for session_id, job in list(st.session_state.profile_background_jobs.items()):
        if session_id in st.session_state.workspaces:
            pct, stage = job["progress"].snapshot()
            name = st.session_state.workspaces[session_id]["name"]
            st.progress(pct, text=f"👥 {name}: {stage}")
    if (not st.session_state.background_jobs and not active_queue
            and not st.session_state.profile_background_jobs):
        st.caption("Không có phiên nào đang chạy nền.")
    if st.session_state.get("_durable_queue_error"):
        st.warning("Không đọc được hàng đợi: "
                   + st.session_state["_durable_queue_error"])


show_background_job_progress()


@st.cache_data(ttl=3600, show_spinner=False, max_entries=100)
def get_thumbnail(video_id):
    """Fetch the highest available YouTube thumbnail only once per cached ID."""
    for quality in ("maxresdefault", "sddefault", "hqdefault", "mqdefault"):
        try:
            response = requests.get(
                f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg",
                timeout=6,
                allow_redirects=False,
            )
            response.raise_for_status()
            with Image.open(BytesIO(response.content)) as thumb:
                if thumb.width >= 300:
                    return response.content
        except (requests.RequestException, OSError, ValueError):
            continue
    return None


# Keep the original preview/download without restoring paid Thumbnail AI editing.
if vid:
    st.subheader("🖼️ Thumbnail gốc chất lượng cao")
    thumbnail = get_thumbnail(vid)
    if thumbnail:
        st.image(thumbnail, width=500)
        with st.container(key="original_thumbnail_download"):
            st.download_button(
                "⬇️ Tải thumbnail gốc", thumbnail,
                file_name=f"thumbnail-{vid}.jpg", mime="image/jpeg",
                type="primary", key=f"thumb_{sid}_{vid}",
            )
    else:
        st.caption("Không lấy được thumbnail gốc từ YouTube cho video này.")


# Original transcript, title and description are retained internally for processing,
# but only target-language results are shown to the user.

with st.container(key="result_tabs"):
    tab_translate, tab_seo, tab_video, tab_characters = st.tabs(
        ["🌍 Bản dịch", "📝 Tiêu đề • Mô tả • SEO",
         "🎬 Form video 8 giây", "🖼️ Ảnh nhân vật"]
    )
with tab_translate:
    if session.get("optimized_script", "").strip():
        with st.expander("✍️ Kịch bản đã tối ưu (dưới 10.000 ký tự)", expanded=False):
            st.caption(
                f"{len(session['optimized_script']):,} ký tự · Giới hạn tối đa 9.999 ký tự. "
                "Giữ nguyên phụ đề gốc để đối chiếu."
            )
            try:
                summary_review = json.loads(session.get("optimization_review_json") or "{}")
            except (ValueError, TypeError):
                summary_review = {}
            if (isinstance(summary_review, dict)
                    and summary_review.get("version") == OPTIMIZATION_VERSION
                    and summary_review.get("source_sha256") == source_hash(session.get("source", ""))
                    and summary_review.get("output_sha256") == source_hash(session["optimized_script"])):
                if summary_review.get("method") == "verbatim":
                    st.caption("Đã rà lỗi nguồn; bản xử lý dưới giới hạn được giữ nguyên ở bước tóm tắt.")
                elif summary_review.get("method") == "repaired_source":
                    st.caption("Đã sửa lỗi nguồn có căn cứ; văn bản dưới giới hạn nên không cần tóm tắt thêm.")
                else:
                    st.caption("Đã rà lỗi nguồn, tóm tắt và đối soát từng phần bằng AI; vẫn có thể còn sai sót.")
                source_repairs = summary_review.get("source_repairs", [])
                if source_repairs:
                    with st.expander(f"🛠️ Các sửa đổi trên bản xử lý ({len(source_repairs)})", expanded=False):
                        for repair in source_repairs:
                            if isinstance(repair, dict):
                                st.markdown("**Trước:** " + str(repair.get("before", "")))
                                st.markdown("**Sau:** " + str(repair.get("after", "")))
                                st.caption(str(repair.get("reason", "")))
                for conflict in summary_review.get("source_conflicts", []):
                    st.warning("Điểm trong bản gốc chưa đủ căn cứ để tự sửa: " + str(conflict))
            else:
                st.info("Kịch bản cũ chưa có kết quả đối soát mới. Chạy lại tạo toàn bộ để tóm tắt lại từ bản gốc.")
            st.code(session["optimized_script"], language=None, wrap_lines=True)
    if st.button(
        "🔄 Chạy lại riêng — Bản dịch", key=f"translate_{sid}",
        disabled=session.get("job_state") == "running",
    ):
        try:
            with st.spinner(f"Đang dịch lại kịch bản đã tối ưu sang {language}..."):
                rerun_translation(
                    session, language,
                    lambda source, target: translate_full_script(source, target),
                    prepare=lambda current: prepare_reviewed_script(current, ai, JobProgress()),
                )
            mark_session_processed(session)
            _persist_and_rerun()
        except Exception as exc:
            st.error(f"Không thể chạy lại Bản dịch: {exc}")
    if session.get("seo_stale") or session.get("character_bible_stale"):
        st.warning(
            "Bản dịch đã thay đổi. SEO, hồ sơ/ảnh nhân vật và form video cũ "
            "có thể không còn khớp; hãy chạy lại các mục phụ thuộc nếu cần."
        )
    copy_all_button(
        "📋 Copy toàn bộ bản dịch",
        session["translated"],
        key=f"copy_all_translation_{sid}",
    )
    with st.expander(f"🌍 Bản dịch hoàn chỉnh ({language}) — Nhấn để xem toàn bộ", expanded=False):
        st.caption("Nội dung đầy đủ; vẫn có thể Copy trong khung hoặc tải TXT.")
        output("📋 Copy toàn bộ bản dịch", session["translated"], allow_download=True)

with tab_seo:
    if st.button(
        "🔄 Chạy lại riêng — Tiêu đề • Mô tả • SEO",
        key=f"seo_{sid}", disabled=session.get("job_state") == "running",
    ):
        try:
            with st.spinner(f"Đang tạo lại SEO bằng {language}..."):
                rerun_seo(session, language, create_target_metadata)
            mark_session_processed(session)
            _persist_and_rerun()
        except Exception as exc:
            st.error(f"Không thể chạy lại SEO: {exc}")
    if session.get("seo_stale"):
        st.warning("SEO đang dựa trên bản dịch cũ. Nhấn Chạy lại riêng để đồng bộ.")
    st.subheader(f"🎬 Tiêu đề đã dịch ({language})")
    copy_all_button(
        "📋 Copy toàn bộ tiêu đề", session.get("new_title", ""),
        key=f"copy_all_title_{sid}",
    )
    output("📋 Copy riêng tiêu đề", session.get("new_title", ""))
    copy_all_button(
        "📋 Copy toàn bộ mô tả", session.get("new_description", ""),
        key=f"copy_all_description_{sid}",
    )
    with st.expander(f"📝 Mô tả đã dịch ({language}) — Nhấn để xem toàn bộ", expanded=False):
        output("📋 Copy riêng mô tả", session.get("new_description", ""))
    st.subheader(f"🔎 Từ khóa SEO ({language})")
    copy_all_button(
        "📋 Copy toàn bộ từ khóa SEO", session.get("seo_tags", ""),
        key=f"copy_all_seo_{sid}",
    )
    output("📋 Copy riêng từ khóa SEO", session.get("seo_tags", ""))
    # Legacy SEO content remains viewable if a saved older session did
    # not have separately generated title, description, and SEO fields.
    if not any(session.get(field) for field in ("new_title", "new_description", "seo_tags")) and session.get("metadata", "").strip():
        st.caption("Nội dung SEO từ bản cũ (chưa được tách các mục):")
        copy_all_button(
            "📋 Copy toàn bộ SEO phiên cũ", session["metadata"],
            key=f"copy_all_legacy_seo_{sid}",
        )
        output("📋 Copy nội dung SEO phiên cũ", session["metadata"])

def launch_video_forms_background(duration, audio_hash, audio_name,
                                  translated, target_language, style,
                                  bible, existing_plan):
    """Start server-side video generation for the selected session only."""
    if sid in st.session_state.video_background_jobs:
        job = st.session_state.video_background_jobs[sid]
        if not job["future"].done():
            raise ValueError("Phiên này đã có tác vụ form video đang chạy.")
    if not key.strip() or not model.strip():
        raise ValueError("Cần API key và model AI hợp lệ.")
    if DURABLE_QUEUE_ENABLED:
        ensure_durable_worker_available()
        _save_cloud_state(force=True)
        queued = submit_job(
            st.secrets, _refresh_login(), sid, "video_forms",
            {
                "translated": translated, "language": target_language,
                "duration_seconds": duration, "audio_hash": audio_hash,
                "audio_name": audio_name, "style": style,
                "character_bible": bible, "existing_plan": existing_plan,
                "provider": provider, "base_url": base_url, "model": model,
                "api_format": api_format, "auth_mode": api_auth_mode,
            },
            {"api_key": key},
        )
        session["video_queue_id"] = queued
        session["video_job_state"] = "running"
        session["video_job_stage"] = "Đã giao tạo form cho worker độc lập"
        session["video_job_percent"] = 0
        session["video_job_error"] = ""
        session["video_job_run_id"] = ""
        session["saved"] = True
        session["processed"] = True
        _persist_and_rerun()
        return
    progress = JobProgress()
    run_id = uuid.uuid4().hex
    snapshot = {
        "sid": sid, "run_id": run_id,
        "translated": translated, "language": target_language,
        "duration_seconds": duration, "audio_hash": audio_hash,
        "audio_name": audio_name, "style": style,
        "character_bible": bible, "existing_plan": existing_plan,
        "provider": provider, "base_url": base_url,
        "model": model, "api_key": key,
        "api_format": api_format, "auth_mode": api_auth_mode,
        "cloud": None,
    }
    if CLOUD_ENABLED:
        auth = _refresh_login()
        snapshot["cloud"] = {
            "auth": dict(auth),
            "secrets": {
                name: str(st.secrets[name])
                for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY",
                             "SESSION_ENCRYPTION_KEY")
            },
        }
    session["video_job_run_id"] = run_id
    session["video_job_state"] = "running"
    session["video_job_error"] = ""
    session["video_job_percent"] = 0
    session["video_job_stage"] = "Đang xếp tác vụ trên máy chủ"
    session["saved"] = True
    session["processed"] = True
    # Write the job identity BEFORE submitting so checkpoints cannot race
    # ahead of a persisted run_id.
    _save_cloud_state(force=True)
    future = get_job_executor().submit(run_video_forms_job, snapshot, progress)
    st.session_state.video_background_jobs[sid] = {
        "future": future, "progress": progress, "run_id": run_id,
    }
    get_job_registry().register(
        run_id, sid, _video_job_scope(), future, progress,
    )
    st.session_state["_session_flash"] = (
        "⏳ Đã tạo tác vụ form video trên máy chủ. "
        "Tiến độ và nội dung được lưu theo từng nhóm form."
    )
    _persist_and_rerun()


def launch_character_profile_background():
    if not key.strip() or not model.strip():
        raise ValueError("Cần API văn bản và model hợp lệ để tạo hồ sơ nhân vật.")
    sync_form(sid)
    snapshot = {
        "translated": session["translated"], "language": language,
        "style": st.session_state.get(f"video_style_{sid}", "Điện ảnh chân thực"),
        "provider": provider, "base_url": base_url, "model": model,
        "api_key": key, "api_format": api_format, "auth_mode": api_auth_mode,
        "cloud": None,
    }
    if CLOUD_ENABLED:
        snapshot["cloud"] = {
            "auth": dict(_refresh_login()),
            "secrets": {name: str(st.secrets[name]) for name in (
                "SUPABASE_URL", "SUPABASE_ANON_KEY", "SESSION_ENCRYPTION_KEY",
            )},
        }
    with _persist_lock:
        collect_profile_background_jobs()
        start_character_job(
            session, sid, snapshot, get_job_executor(), get_job_registry(),
            st.session_state.profile_background_jobs, "characters:" + _job_scope(),
            lambda: _save_cloud_state_unlocked(force=True),
        )
    st.session_state["_session_flash"] = (
        "👥 Đã chạy nền tác vụ hồ sơ nhân vật. Bạn có thể chuyển mục hoặc tải lại trang."
    )
    _persist_and_rerun()


with tab_video:
    render_video_forms(
        session, sid, language,
        ai=ai, api_key=key,
        mark_processed=mark_session_processed,
        persist_and_rerun=_persist_and_rerun,
        launch_video_job=launch_video_forms_background,
    )

with tab_characters:
    if DURABLE_QUEUE_ENABLED and session.get("character_images_manifest"):
        if not IMAGE_STORE.images(_job_scope(), sid):
            try:
                restored = fetch_portrait_images(
                    st.secrets, _refresh_login(), sid,
                    session["character_images_manifest"],
                )
                for name, image_png in restored.items():
                    IMAGE_STORE.save(_job_scope(), sid, name, image_png)
            except Exception as exc:
                st.warning("Chưa tải được ảnh nhân vật từ Storage: " + str(exc)[:180])
    st.subheader("🖼️ Ảnh nhân vật của phiên này")
    # Display the same bible previously shown in Video Forms here instead.
    # Some older sessions only kept the bible inside video_forms JSON.
    character_bible = str(session.get("character_bible") or "").strip()
    raw_video_plan = session.get("video_forms", "")
    if isinstance(raw_video_plan, str) and raw_video_plan:
        try:
            saved_video_plan = json.loads(raw_video_plan)
            if isinstance(saved_video_plan, dict):
                character_bible = (
                    character_bible
                    or str(saved_video_plan.get("character_bible") or "").strip()
                )
        except (ValueError, TypeError):
            pass
    if character_bible:
        copy_all_button(
            "📋 Copy hồ sơ nhân vật/bối cảnh cố định", character_bible,
            key=f"copy_character_bible_{sid}",
        )
    with st.expander(
        "📌 Hồ sơ nhân vật/bối cảnh cố định cho mọi form", expanded=False
    ):
        if character_bible:
            st.code(character_bible, language=None, wrap_lines=True)
        else:
            st.info(
                "Chưa có hồ sơ nhân vật. Hãy chạy BẮT ĐẦU TẠO TOÀN BỘ "
                "hoặc tạo form video 8 giây để hệ thống lập hồ sơ."
            )

    # Profiles are generated from the TARGET translation, not from raw
    # subtitles or images. Older saved sessions can request an upgrade.
    profile_json = session.get("character_profile_json", "")
    saved_sheets = []
    if isinstance(profile_json, str) and profile_json.strip():
        try:
            parsed_profile = json.loads(profile_json)
            saved_sheets = detailed_character_profiles(parsed_profile)
        except (ValueError, TypeError):
            saved_sheets = []
    if not saved_sheets and isinstance(raw_video_plan, str) and raw_video_plan:
        try:
            existing_plan = json.loads(raw_video_plan)
            if isinstance(existing_plan, dict):
                saved_sheets = detailed_character_profiles({
                    "characters": existing_plan.get("character_profiles", []),
                    "character_bible": character_bible,
                })
        except (ValueError, TypeError):
            pass
    if not saved_sheets and character_bible:
        saved_sheets = detailed_character_profiles({
            "character_bible": character_bible,
        })

    st.caption(
        f"Tạo tối đa {MAX_DETAILED_CHARACTERS} hồ sơ nhân vật; ưu tiên nhân vật "
        "chính và nhân vật xuất hiện nhiều trong bản dịch."
    )
    current_profile_job = profile_job(session)
    profile_running = current_profile_job.get("state") == "running"
    st.caption(
        "Tác vụ chạy nền trên máy chủ, tự lưu tiến độ và tiếp tục khi bạn "
        "chuyển mục hoặc tải lại trang."
    )
    if profile_running:
        active_profile_job = st.session_state.profile_background_jobs.get(sid)
        if active_profile_job:
            percent, stage = active_profile_job["progress"].snapshot()
        else:
            percent = current_profile_job.get("percent", 0)
            stage = current_profile_job.get("stage", "Đang chạy nền")
        st.progress(int(percent), text=stage)
    elif current_profile_job.get("state") == "completed":
        st.success("Đã hoàn thành và lưu hồ sơ nhân vật.")
    elif current_profile_job.get("state") in ("failed", "interrupted"):
        st.error("Tác vụ hồ sơ chưa hoàn thành: " + current_profile_job.get("error", ""))
        st.caption("Nhấn tạo/cập nhật để tiếp tục từ phần đã lưu. Kiểm tra API nếu lỗi vẫn xảy ra.")
    if current_profile_job.get("save_error"):
        st.warning(current_profile_job["save_error"])
    if st.button(
        "🔄 Tạo/cập nhật hồ sơ chi tiết từng nhân vật",
        key=f"regenerate_detailed_characters_{sid}",
        disabled=not bool(session.get("translated", "").strip())
                 or session.get("job_state") == "running" or profile_running,
    ):
        try:
            launch_character_profile_background()
        except Exception as exc:
            st.error("Chưa thể khởi động tác vụ hồ sơ: " + str(exc)[:300])

    st.markdown("**👥 Hồ sơ ảnh tham chiếu theo từng nhân vật**")
    if saved_sheets:
        st.caption(
            f"Đã nhận diện {len(saved_sheets)} nhân vật. "
            "Mỗi hồ sơ mở/thu gọn riêng, phục vụ tạo ảnh tham chiếu "
            "giữ nguyên diện mạo trong tất cả các cảnh."
        )
        copy_all_button(
            "📋 Copy toàn bộ hồ sơ nhân vật",
            "\n\n".join(character_profile_text(sheet) for sheet in saved_sheets),
            key=f"copy_all_character_profiles_{sid}",
        )
        for idx, sheet in enumerate(saved_sheets, start=1):
            # Copy stays available even while the character's form is collapsed.
            copy_all_button(
                f"📋 Copy hồ sơ — {sheet['name']}",
                character_profile_text(sheet),
                key=f"copy_character_reference_{sid}_{idx}",
            )
            with st.expander(
                f"👤 Nhân vật {idx:02d} — {sheet['name']}", expanded=False,
            ):
                revision = hashlib.sha256(
                    json.dumps(sheet, ensure_ascii=False, sort_keys=True).encode()
                ).hexdigest()[:12]
                form_key = f"character_profile_{sid}_{idx}_{revision}"
                with st.form(form_key):
                    st.text_input("Tên nhân vật", value=sheet["name"], disabled=True,
                                  key=f"{form_key}_name")
                    edited = dict(sheet)
                    edited["description"] = st.text_area(
                        "Nhận diện tổng quan", value=sheet.get("description", ""),
                        key=f"{form_key}_description",
                    )
                    for field, field_label in CHARACTER_PROFILE_FIELDS:
                        edited[field] = st.text_area(
                            field_label, value=sheet.get(field, ""),
                            key=f"{form_key}_{field}", height=100,
                        )
                    st.caption(
                        "Ghi rõ chi tiết trong bản dịch và chi tiết đề xuất tạo hình. "
                        "Lưu hồ sơ trước khi sao chép hoặc tạo lại ảnh tham chiếu."
                    )
                    save_profile = st.form_submit_button(
                        "💾 Lưu hồ sơ nhân vật",
                        disabled=session.get("job_state") == "running" or profile_running,
                    )
                if save_profile:
                    saved_sheets[idx - 1] = edited
                    updated_profile = {
                        "characters": saved_sheets,
                        "character_bible": "\n\n".join(
                            character_profile_text(item) for item in saved_sheets
                        ),
                    }
                    session["character_profile_json"] = json.dumps(
                        updated_profile, ensure_ascii=False,
                    )
                    session["character_profile"] = updated_profile
                    session["character_bible"] = updated_profile["character_bible"]
                    mark_session_processed(session)
                    _persist_and_rerun()

    else:
        st.info(
            "Chưa có hồ sơ chi tiết. Nhấn 'Tạo/cập nhật hồ sơ chi tiết "
            "từng nhân vật' để trích xuất từ bản dịch đích."
        )

    st.caption(
        "Ảnh được tự tạo sau Hồ sơ nhân vật nếu đã nhập OpenAI Images API key. "
        "Chỉ chứa nhân vật thuộc phiên hiện tại, không lẫn phiên khác."
    )
    if st.button(
        "🔄 Chạy lại riêng — Ảnh nhân vật",
        key=f"retry_character_images_{sid}",
        disabled=session.get("job_state") == "running",
    ):
        if not image_api_key:
            st.warning("Hãy nhập OpenAI Images API key trước khi chạy lại ảnh.")
        elif not key.strip():
            st.warning("Hãy nhập API văn bản để nhận diện nhân vật từ hồ sơ.")
        else:
            try:
                with st.spinner("Đang phân tích lại hồ sơ và tạo ảnh nhân vật..."):
                    style = st.session_state.get(f"video_style_{sid}", "Điện ảnh chân thực")
                    bible, specs, changed = portrait_retry_specs(session, language, style, ai)
                    if saved_sheets and not session.get("character_bible_stale"):
                        specs = [
                            (sheet["name"], character_reference_description(sheet))
                            for sheet in saved_sheets[:8]
                        ]
                    if not specs:
                        raise ValueError("Hồ sơ không có nhân vật được nhận diện.")
                    failures = []
                    successes = 0
                    for name, desc in specs:
                        try:
                            png = create_character_png(
                                image_api_key, name, desc, style=style,
                                bible=bible, model=IMAGE_MODEL,
                            )
                            IMAGE_STORE.save(_job_scope(), sid, name, png)
                            successes += 1
                        except Exception as error:
                            failures.append(f"{name}: {str(error).replace(image_api_key, '[KEY ĐÃ ẨN]')}")
                    if successes:
                        if changed:
                            session["character_bible"] = bible
                            session["character_bible_stale"] = False
                        session["character_images_error"] = (
                            "Một số ảnh chưa tạo được: " + "; ".join(failures)
                        )[:350] if failures else ""
                        mark_session_processed(session)
                        _persist_and_rerun()
                    else:
                        raise ValueError("Không tạo được ảnh nào. " + "; ".join(failures))
            except Exception as exc:
                st.error(f"Không thể chạy lại ảnh nhân vật: {exc}")
    if session.get("character_bible_stale"):
        st.warning("Hồ sơ nhân vật có thể không còn khớp bản dịch mới.")
    scene_images = IMAGE_STORE.images(_job_scope(), sid)
    if scene_images:
        st.success(f"Đã có {len(scene_images)} ảnh nhân vật.")
        for person_name, image_png in scene_images.items():
            st.markdown(f"**{person_name}**")
            st.image(image_png, width=260)
        archive_name, archive_data = session_images_zip(
            scene_images, session["name"]
        )
        st.download_button(
            "⬇️ Tải tất cả ảnh nhân vật của phiên (.ZIP)",
            archive_data,
            file_name=archive_name,
            mime="application/zip",
            key=f"download_character_images_zip_{sid}",
            use_container_width=True,
            type="primary",
        )
        st.caption(
            "Muốn chọn thư mục lưu, bật tùy chọn trình duyệt 'Hỏi vị trí lưu "
            "mỗi file trước khi tải xuống'."
        )
    elif session.get("job_state") == "running":
        st.info("Đang chờ hoàn thành Hồ sơ nhân vật / tạo ảnh...")
    elif not image_api_key:
        st.warning("Hãy nhập OpenAI Images API key trong thanh bên để tự tạo ảnh ở phiên mới.")
    else:
        st.info("Phiên này chưa có ảnh; hãy chạy BẮT ĐẦU TẠO TOÀN BỘ.")
    if session.get("character_images_error"):
        st.warning(str(session["character_images_error"]))
        if "401" in str(session["character_images_error"]):
            st.info(
                "Ảnh chưa tạo được vì OpenAI API key bị từ chối. "
                "Mở mục 🖼️ API tạo ảnh nhân vật ở thanh bên, kiểm tra "
                "hoặc thay key, rồi bấm 🔄 Chạy lại riêng — Ảnh nhân vật. "
                "Không cần chạy lại BẮT ĐẦU TẠO TOÀN BỘ."
            )

st.caption("📋 Nút Copy toàn bộ nằm ngay bên ngoài từng mục và sao chép đầy đủ nội dung, kể cả khi khung xem đang thu gọn.")

# Automatically save changed sessions and ALL manually-entered API provider
# settings/keys, encrypted, after widgets update on each Streamlit rerun.
_save_cloud_state()
_save_browser_api_settings()
_save_browser_sessions()
if st.session_state.pop("_browser_delete_confirmed", False):
    st.caption("✅ Đã cập nhật bản lưu trình duyệt sau khi xóa phiên.")
if st.session_state.get("_browser_delete_revision"):
    st.caption("💾 Đang xác nhận xóa dữ liệu phiên khỏi bộ nhớ trình duyệt...")
if not CLOUD_ENABLED and st.session_state.get("_browser_restore_success"):
    st.caption("💾 Đã khôi phục danh sách phiên từ trình duyệt này.")
if not CLOUD_ENABLED and st.session_state.get("_browser_api_error"):
    st.warning(
        "⚠️ Cấu hình API chưa được tự lưu trên trình duyệt: "
        + st.session_state["_browser_api_error"]
        + " Có thể dùng Supabase để lưu mã hóa theo tài khoản."
    )
if not CLOUD_ENABLED and st.session_state.get("_browser_save_error"):
    st.warning(
        "⚠️ Không thể tự lưu danh sách phiên: "
        + st.session_state["_browser_save_error"]
        + " Hãy giữ dữ liệu website hoặc bật Supabase để lưu phiên lâu dài."
    )
if CLOUD_ENABLED:
    if st.session_state.get("_cloud_save_error"):
        st.warning(
            "⚠️ Chưa đồng bộ được phiên hoặc API lên lưu trữ đám mây: "
            + st.session_state["_cloud_save_error"]
        )
    else:
        st.caption("☁️ Phiên, bản dịch và cấu hình API được đồng bộ cho lần đăng nhập tiếp theo.")


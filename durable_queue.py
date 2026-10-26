"""Authenticated durable job submission and status reconciliation.

Streamlit only INSERTs and SELECTs its own queue rows through Supabase RLS.
No database admin credential is used here. API secrets are Fernet encrypted
before the queue record is written and never returned in status queries.
"""
import json
import re
from datetime import datetime, timezone

from persistent_store import get_config, _request, _user_headers


JOB_TYPES = {"full", "video_forms"}
VISIBLE_FIELDS = {
    "source", "title", "description", "optimized_script", "translated",
    "language", "new_title", "new_description", "seo_tags", "metadata",
    "character_bible", "character_images_error", "character_images_manifest",
    "video_forms",
}
VISIBLE_STATUSES = {"queued", "running", "retry_wait", "completed", "failed"}


def queue_available(secrets):
    """Explicit opt-in only once an independent worker has been deployed."""
    return str(secrets.get("DURABLE_WORKER_ENABLED", "")).strip().lower() in (
        "true", "1", "yes", "on",
    )


def _valid_sid(sid):
    return isinstance(sid, str) and re.fullmatch(r"[a-f0-9]{32}", sid) is not None


def submit_job(secrets, auth, sid, kind, snapshot, credential_values):
    if not _valid_sid(sid) or kind not in JOB_TYPES:
        raise ValueError("Mã phiên hoặc loại công việc không hợp lệ.")
    if not isinstance(snapshot, dict) or not isinstance(credential_values, dict):
        raise ValueError("Dữ liệu công việc không hợp lệ.")
    text_key = credential_values.get("api_key", "")
    if not isinstance(text_key, str) or not text_key.strip():
        raise ValueError("Chưa nhập API key cho nhà cung cấp AI.")
    # Passwords are never written as plaintext into the durable job payload.
    secret_words = ("api_key", "supadata_key", "image_api_key", "token",
                    "password", "secret", "authorization")
    if any(any(word in str(field).lower() for word in secret_words)
           for field in snapshot):
        raise ValueError("Không được lưu thông tin xác thực trong payload.")
    url, anon, cipher = get_config(secrets)
    keys_blob = cipher.encrypt(
        json.dumps(credential_values, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    request = [{
        "user_id": auth["user_id"], "session_id": sid,
        "kind": kind, "snapshot": snapshot, "encrypted_keys": keys_blob,
    }]
    response = _request(
        "POST", url + "/rest/v1/lmt_durable_jobs",
        {**_user_headers(anon, auth), "Prefer": "return=representation"},
        json=request, params={"select": "id,session_id,kind,status"},
    )
    if not isinstance(response, list) or not response:
        raise RuntimeError("Hàng đợi không xác nhận đã nhận công việc.")
    job = response[0]
    if job.get("session_id") != sid or job.get("kind") != kind:
        raise RuntimeError("Máy chủ hàng đợi trả về phiên không khớp.")
    return job["id"]


def get_owned_jobs(secrets, auth, *, limit=150):
    url, anon, _ = get_config(secrets)
    rows = _request(
        "GET", url + "/rest/v1/lmt_durable_jobs",
        _user_headers(anon, auth),
        params={
            "select": "id,session_id,kind,status,result,progress,stage,error,attempts,updated_at",
            "user_id": "eq." + str(auth["user_id"]),
            "order": "created_at.desc",
            "limit": str(min(150, max(1, int(limit)))),
        },
    )
    if not isinstance(rows, list):
        raise RuntimeError("Hàng đợi trả danh sách không hợp lệ.")
    return rows


def apply_owned_job_results(workspaces, jobs):
    """Overlay newest queue checkpoints only onto the exact linked session.

    The job id is saved in the user session. This prevents an old run or
    another session's output from replacing newer work.
    """
    changed = False
    for job in reversed(jobs):
        if not isinstance(job, dict):
            continue
        sid, kind, status = job.get("session_id"), job.get("kind"), job.get("status")
        if not _valid_sid(sid) or kind not in JOB_TYPES or status not in VISIBLE_STATUSES:
            continue
        session = workspaces.get(sid)
        if not isinstance(session, dict):
            continue
        id_field = "video_queue_id" if kind == "video_forms" else "job_queue_id"
        if session.get(id_field) != job.get("id"):
            continue
        fields = job.get("result") or {}
        if isinstance(fields, dict):
            for field, val in fields.items():
                if field in VISIBLE_FIELDS and isinstance(val, str) and session.get(field) != val:
                    session[field] = val
                    changed = True
        prefix = "video_job_" if kind == "video_forms" else "job_"
        progress = job.get("progress", 0)
        if not isinstance(progress, int):
            progress = 0
        values = {
            prefix + "state": "running" if status in ("queued", "running", "retry_wait") else status,
            prefix + "percent": min(100, max(0, progress)),
            prefix + "stage": str(job.get("stage") or status)[:140],
            prefix + "error": str(job.get("error") or "")[:700],
        }
        for key, val in values.items():
            if session.get(key) != val:
                session[key] = val
                changed = True
        if not session.get("saved") or not session.get("processed"):
            session["saved"] = True
            session["processed"] = True
            changed = True
    return changed


def worker_healthy(secrets, auth, *, max_age_seconds=150):
    """Verify a live independent worker, not merely a configured toggle."""
    url, anon, _ = get_config(secrets)
    rows = _request(
        "GET", url + "/rest/v1/lmt_worker_health",
        _user_headers(anon, auth),
        params={
            "select": "name,last_seen",
            "order": "last_seen.desc", "limit": "1",
        },
    )
    if not isinstance(rows, list) or not rows:
        return False
    stamp = str(rows[0].get("last_seen") or "")
    try:
        touched = datetime.fromisoformat(stamp.replace("Z","+00:00"))
        return 0 <= (datetime.now(timezone.utc) - touched).total_seconds() <= max_age_seconds
    except (ValueError,TypeError):
        return False


def fetch_portrait_images(secrets, auth, sid, raw_manifest):
    """Fetch private PNGs via user's own JWT; the UI never needs service key."""
    if not _valid_sid(sid) or not raw_manifest:
        return {}
    import requests
    try:
        manifest = json.loads(raw_manifest)
    except (TypeError,ValueError):
        return {}
    if not isinstance(manifest,dict):
        return {}
    url, anon, _ = get_config(secrets)
    prefix = str(auth["user_id"]) + "/" + sid + "/"
    images = {}
    for name,path in list(manifest.items())[:8]:
        if not isinstance(name,str) or not isinstance(path,str):
            continue
        if not path.startswith(prefix) or "/" in path[len(prefix):] or len(path) > 240:
            continue
        try:
            result = requests.get(
                url + "/storage/v1/object/lmt-character-images/" + path,
                headers=_user_headers(anon,auth), timeout=(7,20),
            )
            if (result.ok and len(result.content) <= 6 * 1024 * 1024
                    and result.content.startswith(b"\\x89PNG\\r\\n\\x1a\\n")):
                images[name] = result.content
        except requests.RequestException:
            continue
    return images

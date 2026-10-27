"""Process-local background video form generation with optional durable checkpoints.

Server workers use immutable settings, never Streamlit UI/session_state.
Signed-in Supabase users have a checkpoint after each validated batch, even
if their laptop sleeps. App servers can still be reclaimed: no guarantee
of uninterrupted processing after a Streamlit Cloud worker restart.
"""
import json
import threading
import time

from api_clients import generate_text
from provider_retries import retry_transient_provider
from groq_pacing import groq_request_gate
from video_scene_planner import character_bible_prompt, parse_json_object
from voice_alignment import duration_weighted_plan
from video_forms_ui import _generate_all_remaining, _completed_count

_persist_lock = threading.RLock()


def _provider_call(snapshot, prompt):
    args = {}
    if snapshot["provider"] == "API bên thứ ba (tùy chỉnh)":
        args = {
            "api_format": snapshot.get("api_format", "chat"),
            "auth_mode": snapshot.get("auth_mode", "bearer"),
        }
    return generate_text(
        snapshot["provider"], snapshot["base_url"], snapshot["model"],
        snapshot["api_key"], prompt, **args,
    )


def save_cloud_video_checkpoint(snapshot, encoded, state, error=""):
    """Patch only the relevant session inside the latest account row.

    Uses user-bound JWT and RLS, never a Supabase admin/service-role key.
    """
    cloud = snapshot.get("cloud")
    if not cloud:
        return
    from persistent_store import (
        get_config, _request, _user_headers, save_user,
    )
    import json as _json
    import time
    with _persist_lock:
        secrets = cloud["secrets"]
        auth = cloud["auth"]
        # Rotating refresh tokens in a worker could invalidate the browser
        # login when the user opens their laptop again.
        if time.time() >= auth["expires_at"]:
            raise RuntimeError(
                "Phiên lưu trữ đã hết hạn khi máy chủ đang xử lý. "
                "Mở lại ứng dụng để đăng nhập và tiếp tục từ form đã lưu."
            )
        url, anon, cipher = get_config(secrets)
        rows = _request(
            "GET", url + "/rest/v1/youtube_studio_state",
            _user_headers(anon, auth),
            params={
                "select": "payload,encrypted_config",
                "user_id": "eq." + auth["user_id"], "limit": "1",
            },
        )
        if not rows:
            raise RuntimeError("Không thấy tài khoản lưu trữ để ghi checkpoint.")
        row = rows[0]
        payload = row["payload"]
        record = payload.get("workspaces", {}).get(snapshot["sid"])
        if not isinstance(record, dict) or record.get("video_job_run_id") != snapshot["run_id"]:
            raise RuntimeError("Phiên đã được xóa hoặc thay thế; dừng lưu form cũ.")
        record["video_forms"] = encoded
        record["video_job_state"] = state
        record["video_job_error"] = str(error)[:300]
        total = len(_json.loads(encoded).get("scenes", []))
        completed = sum(
            bool(x.get("visual_prompt", "").strip())
            for x in _json.loads(encoded).get("scenes", [])
        )
        record["video_job_percent"] = round(100 * completed / total) if total else 0
        record["video_job_stage"] = f"Đã tạo {completed}/{total} form"
        settings = {}
        if row.get("encrypted_config"):
            settings = _json.loads(cipher.decrypt(
                row["encrypted_config"].encode("ascii")
            ).decode("utf-8"))
        save_user(secrets, auth, payload, settings)


def run_video_forms_job(snapshot, progress):
    """Resume or generate all forms; checkpoint after each six-scene API batch."""
    fields = {}
    plan = None
    def call_with_retry(prompt):
        def wait(seconds):
            remaining = seconds
            while remaining > 0:
                progress.check_cancelled()
                step = min(1.0, remaining)
                time.sleep(step)
                remaining -= step
            progress.check_cancelled()

        def report(message):
            completed = _completed_count(plan) if plan else 0
            total = len(plan.get("scenes", [])) if plan else 0
            percent = round(100 * completed / total) if total else 0
            progress.update(percent, message)

        def request():
            progress.check_cancelled()
            with groq_request_gate.reporting(progress):
                return _provider_call(snapshot, prompt)
        return retry_transient_provider(request, report=report, wait=wait)

    try:
        progress.check_cancelled()
        if snapshot.get("existing_plan"):
            plan = json.loads(snapshot["existing_plan"])
        else:
            progress.update(0, "🎧 Ước tính số form theo thời lượng audio")
            plan = duration_weighted_plan(
                snapshot["translated"], snapshot["language"],
                snapshot["duration_seconds"],
            )
            plan["audio_sha256"] = snapshot["audio_hash"]
            plan["audio_filename"] = snapshot["audio_name"]
            bible = snapshot.get("character_bible", "").strip()
            if not bible:
                progress.update(0, "👤 Đang tạo hồ sơ nhân vật cố định")
                response = parse_json_object(
                    call_with_retry(character_bible_prompt(
                        snapshot["translated"], snapshot["language"],
                        snapshot["style"],
                    )),
                    "character_bible",
                )
                bible = response["character_bible"]
                if isinstance(response.get("characters"), list):
                    plan["character_profiles"] = response["characters"]
            if not isinstance(bible, str) or not bible.strip():
                raise ValueError("Không tạo được hồ sơ nhân vật.")
            plan["character_bible"] = bible.strip()
            plan["style"] = snapshot["style"]

        def checkpoint(current):
            progress.check_cancelled()
            encoded = json.dumps(current, ensure_ascii=False)
            if len(encoded) > 390000:
                raise ValueError("Form video quá lớn để lưu trong phiên.")
            fields["video_forms"] = encoded
            progress.publish("video_forms", encoded)
            completed, total = _completed_count(current), len(current["scenes"])
            percent = round(100 * completed / total) if total else 0
            progress.update(percent, f"🎬 Đang tạo form: {completed}/{total} ({percent}%)")
            # The signed-in user's checkpoint persists without a browser poll.
            save_cloud_video_checkpoint(snapshot, encoded, "running")

        checkpoint(plan)
        _generate_all_remaining(
            plan, call_with_retry,
            checkpoint=checkpoint,
        )
        final = fields["video_forms"]
        save_cloud_video_checkpoint(snapshot, final, "completed")
        progress.update(100, f"✅ Hoàn thành {len(plan['scenes'])} form")
        return {"ok": True, "fields": fields, "error": ""}
    except Exception as exc:
        # Do not expose any API secret that may appear in vendor error messages.
        message = str(exc)
        for key in (snapshot.get("api_key", ""),):
            if key:
                message = message.replace(key, "[API KEY ĐÃ ẨN]")
        if plan is not None:
            try:
                encoded = json.dumps(plan, ensure_ascii=False)
                fields["video_forms"] = encoded
                progress.publish("video_forms", encoded)
                save_cloud_video_checkpoint(snapshot, encoded, "failed", message)
            except Exception:
                pass
        return {"ok": False, "fields": fields, "error": message[:300]}



def save_cloud_full_checkpoint(snapshot, fields, state, error=""):
    """Persist full-translation stages directly from worker without browser."""
    cloud = snapshot.get("cloud")
    if not cloud:
        return
    import time
    from persistent_store import (
        CONTENT_FIELDS, get_config, _request, _user_headers, save_user,
    )
    with _persist_lock:
        auth, secrets = cloud["auth"], cloud["secrets"]
        if time.time() >= auth["expires_at"]:
            raise RuntimeError(
                "Phiên xác thực lưu trữ hết hạn khi chạy nền. "
                "Kết quả trong bộ nhớ máy chủ được giữ để tiếp tục."
            )
        url, anon, cipher = get_config(secrets)
        rows = _request(
            "GET", url + "/rest/v1/youtube_studio_state",
            _user_headers(anon, auth),
            params={
                "select": "payload,encrypted_config",
                "user_id": "eq." + auth["user_id"], "limit": "1",
            },
        )
        if not rows:
            raise RuntimeError("Không tìm thấy tài khoản để lưu tiến trình dịch.")
        row = rows[0]
        payload = row["payload"]
        record = payload.get("workspaces", {}).get(snapshot["sid"])
        if not isinstance(record, dict) or record.get("job_run_id") != snapshot["run_id"]:
            raise RuntimeError("Phiên dịch đã bị xóa hoặc được thay thế.")
        record.update({k: v for k, v in fields.items() if k in CONTENT_FIELDS})
        record["job_state"] = state
        record["job_error"] = str(error)[:700]
        record["saved"] = True
        record["processed"] = True
        settings = {}
        if row.get("encrypted_config"):
            settings = json.loads(cipher.decrypt(
                row["encrypted_config"].encode("ascii")
            ).decode("utf-8"))
        save_user(secrets, auth, payload, settings)


class _FullJobProgressProxy:
    """Publish translation/SEO partials to both process memory and account DB."""

    def __init__(self, snapshot, progress):
        self.job_snapshot, self.progress = snapshot, progress

    def publish(self, field, value):
        self.progress.publish(field, value)
        save_cloud_full_checkpoint(
            self.job_snapshot, self.progress.partial_result(), "running",
        )

    def __getattr__(self, key):
        return getattr(self.progress, key)


def run_full_job_with_server_saves(snapshot, progress):
    """Existing full workflow unchanged; independently save each finished stage."""
    from background_jobs import run_full_job
    result = run_full_job(snapshot, _FullJobProgressProxy(snapshot, progress))
    try:
        save_cloud_full_checkpoint(
            snapshot, result.get("fields", {}),
            "completed" if result.get("ok") else "failed",
            result.get("error", ""),
        )
    except Exception as exc:
        result["ok"] = False
        result["error"] = (
            "Máy chủ chưa xác nhận lưu kết quả vào tài khoản: "
            + str(exc)[:300]
        )
    return result

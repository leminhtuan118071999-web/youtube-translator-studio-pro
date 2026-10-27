"""Character workers survive browser reruns/reloads within the server process."""
import json
import time
import uuid

import requests

from api_clients import RateLimitError, TransientProviderError
from background_jobs import JobProgress
from character_profiles import build_character_profiles, source_chunks, MAX_DETAILED_CHARACTERS
from server_video_jobs import _provider_call, _persist_lock
from video_scene_planner import source_fingerprint


def profile_data(record):
    try:
        data = json.loads(record.get("character_profile_json") or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def profile_job(record):
    job = profile_data(record).get("_profile_job", {})
    return job if isinstance(job, dict) else {}


class SupersededProfileJob(RuntimeError):
    pass


def save_character_checkpoint(snapshot, fields):
    """Patch the matching user's profile fields without touching other sessions."""
    cloud = snapshot.get("cloud")
    if not cloud:
        return
    from persistent_store import get_config, _request, _user_headers, save_user
    with _persist_lock:
        auth, secrets = cloud["auth"], cloud["secrets"]
        if time.time() >= auth["expires_at"]:
            raise RuntimeError("Phiên lưu trữ hết hạn; kết quả vẫn được giữ trong bộ nhớ máy chủ.")
        url, anon, cipher = get_config(secrets)
        rows = _request(
            "GET", url + "/rest/v1/youtube_studio_state", _user_headers(anon, auth),
            params={"select": "payload,encrypted_config", "limit": "1",
                    "user_id": "eq." + auth["user_id"]},
        )
        if not rows:
            raise SupersededProfileJob("Không còn tài khoản lưu trữ của tác vụ.")
        row = rows[0]
        payload = row["payload"]
        record = payload.get("workspaces", {}).get(snapshot["sid"])
        if (not isinstance(record, dict)
                or profile_job(record).get("run_id") != snapshot["run_id"]
                or record.get("translated", "").strip() != snapshot["translated"].strip()
                or record.get("language", "") != snapshot["language"]):
            raise SupersededProfileJob("Phiên đã bị xóa, bản dịch hoặc tác vụ đã thay đổi.")
        for field in ("character_profile_json", "character_bible"):
            if field in fields:
                record[field] = fields[field]
        record["saved"] = record["processed"] = True
        settings = {}
        if row.get("encrypted_config"):
            settings = json.loads(cipher.decrypt(row["encrypted_config"].encode()).decode())
        save_user(secrets, auth, payload, settings)


def run_character_job(snapshot, progress):
    """Use immutable settings; never call Streamlit from the worker thread."""
    data = profile_data(snapshot)
    meta = dict(data["_profile_job"])
    fields = {}

    def publish():
        meta.pop("save_error", None)
        percent, stage = progress.snapshot()
        meta.update(percent=percent, stage=stage)
        data["_profile_job"] = dict(meta)
        fields["character_profile_json"] = json.dumps(data, ensure_ascii=False)
        for field, value in fields.items():
            progress.publish(field, value)
        try:
            save_character_checkpoint(snapshot, fields)
        except SupersededProfileJob:
            progress.cancel()
            raise
        except Exception:
            # Losing storage connectivity must not stop paid AI work. The
            # registry retains results, which the browser can save on return.
            meta["save_error"] = "Chưa đồng bộ được; kết quả đang được giữ trên máy chủ."
            data["_profile_job"] = dict(meta)
            fields["character_profile_json"] = json.dumps(data, ensure_ascii=False)
            progress.publish("character_profile_json", fields["character_profile_json"])

    def report(message):
        progress.check_cancelled()
        progress.update(0, message)
        publish()

    def checkpoint(state):
        progress.check_cancelled()
        data["_profile_build"] = state
        scan_fraction = state["scanned"] / max(1, len(source_chunks(snapshot["translated"])))
        total = min(MAX_DETAILED_CHARACTERS, len(state["evidence"]))
        fraction = 40 * scan_fraction + 59 * len(state["sheets"]) / max(1, total)
        progress.update(fraction, progress.snapshot()[1])
        publish()

    def call(prompt):
        for attempt in range(4):
            progress.check_cancelled()
            try:
                result = _provider_call(snapshot, prompt)
                progress.check_cancelled()
                return result
            except Exception as exc:
                cause = exc.__cause__
                retryable = (
                    isinstance(exc, TransientProviderError)
                    or isinstance(exc, RateLimitError) and exc.can_retry
                    or isinstance(cause, (requests.Timeout, requests.ConnectionError))
                    and not isinstance(cause, requests.exceptions.SSLError)
                )
                if not retryable or attempt == 3:
                    raise
                wait = min(120, max(3, float(getattr(exc, "retry_after", None) or 3 * 2**attempt)))
                report(f"API tạm gián đoạn; tự thử lại {attempt + 1}/3 sau {int(wait)} giây")
                while wait > 0:
                    progress.check_cancelled()
                    time.sleep(min(1, wait))
                    wait -= 1

    try:
        profile = build_character_profiles(
            snapshot["translated"], snapshot["language"], snapshot["style"], call,
            state=data.get("_profile_build"), checkpoint=checkpoint, report=report,
        )
        if not profile["characters"]:
            raise ValueError("AI chưa nhận diện được nhân vật có tên.")
        progress.check_cancelled()
        data = profile
        meta.update(state="completed", error="")
        fields["character_bible"] = profile["character_bible"]
        progress.update(100, f"Hoàn thành {len(profile['characters'])} hồ sơ nhân vật")
        publish()
        return {"ok": True, "fields": dict(fields), "error": ""}
    except Exception as exc:
        error = str(exc).replace(snapshot["api_key"], "[API KEY ĐÃ ẨN]")[:450]
        meta.update(state="failed", error=error)
        try:
            publish()
        except SupersededProfileJob:
            pass
        return {"ok": False, "fields": dict(fields), "error": error}


def start_character_job(record, sid, snapshot, executor, registry, jobs, scope, persist):
    existing = profile_job(record)
    if existing.get("state") == "running":
        job = registry.lookup(existing.get("run_id"), sid, scope)
        if job:
            jobs[sid] = job
            return False
    run_id = uuid.uuid4().hex
    data = profile_data(record)
    data["_profile_job"] = {
        "run_id": run_id, "state": "running", "error": "", "percent": 0,
        "stage": "Đang xếp tác vụ hồ sơ trên máy chủ",
        "source_hash": source_fingerprint(snapshot["translated"], snapshot["language"]),
    }
    record["character_profile_json"] = json.dumps(data, ensure_ascii=False)
    record["saved"] = record["processed"] = True
    try:
        persist()
        snapshot = dict(snapshot, sid=sid, run_id=run_id,
                        character_profile_json=record["character_profile_json"])
        progress = JobProgress()
        future = executor.submit(run_character_job, snapshot, progress)
        registry.register(run_id, sid, scope, future, progress)
    except Exception:
        data["_profile_job"].update(state="failed", error="Chưa khởi động được tác vụ nền; hãy thử lại.")
        record["character_profile_json"] = json.dumps(data, ensure_ascii=False)
        raise
    jobs[sid] = {"run_id": run_id, "future": future, "progress": progress}
    return True


def collect_character_jobs(workspaces, jobs, registry, scope):
    """Reattach by owner/session/run ID, then collect partials and final results."""
    changed = False
    for sid, record in workspaces.items():
        meta = profile_job(record)
        if meta.get("state") != "running" or sid in jobs:
            continue
        job = registry.lookup(meta.get("run_id"), sid, scope)
        if job:
            jobs[sid] = job
        else:
            data = profile_data(record)
            meta.update(state="interrupted", error="Máy chủ đã dừng tác vụ. Nhấn tạo/cập nhật để tiếp tục từ tiến độ đã lưu.")
            data["_profile_job"] = meta
            record["character_profile_json"] = json.dumps(data, ensure_ascii=False)
            changed = True
    for sid, job in list(jobs.items()):
        record = workspaces.get(sid)
        meta = profile_job(record or {})
        stale = (not record or meta.get("run_id") != job["run_id"]
                 or meta.get("source_hash") != source_fingerprint(
                     record.get("translated", ""), record.get("language", "")))
        if stale:
            registry.cancel(job["run_id"], sid, scope)
            jobs.pop(sid, None)
            if record and meta.get("run_id") == job["run_id"]:
                data = profile_data(record)
                meta.update(state="interrupted", error="Bản dịch/ngôn ngữ đã đổi; hãy tạo hồ sơ theo nội dung mới.")
                data["_profile_job"] = meta
                record["character_profile_json"] = json.dumps(data, ensure_ascii=False)
                changed = True
            continue
        fields = job["progress"].partial_result()
        if job["future"].done():
            try:
                fields.update(job["future"].result().get("fields", {}))
            except Exception:
                data = profile_data(record)
                data["_profile_job"].update(state="failed", error="Tác vụ nền kết thúc ngoài dự kiến.")
                fields["character_profile_json"] = json.dumps(data, ensure_ascii=False)
            jobs.pop(sid, None)
            # Keep the completed registry entry for 24h: a browser may reload
            # with an older 'running' backup before its final snapshot is saved.
        for field in ("character_profile_json", "character_bible"):
            if field in fields and record.get(field) != fields[field]:
                record[field] = fields[field]
                changed = True
        if profile_job(record).get("state") == "completed":
            record["character_bible_stale"] = False
            record["saved"] = record["processed"] = True
    return changed

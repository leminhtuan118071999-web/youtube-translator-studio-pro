"""Independent durable queue worker (e.g. Render Background Worker).

Run: python durable_worker.py
Requires DATABASE_URL, SESSION_ENCRYPTION_KEY. Optional Supabase Storage
credentials are needed only to persist generated character portraits.
The worker remains independent of Streamlit Cloud, can restart, and safely
reclaims expired leases. No UI calls or local browser state are used.
"""
import json
import logging
import os
import random
import re
import signal
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from background_jobs import JobProgress, run_full_job
from server_video_jobs import run_video_forms_job

LOG = logging.getLogger("lmt.durable_worker")
LEASE_SECONDS = 180
HEARTBEAT_SECONDS = 25
POLL_SECONDS = 5
FIELDS_LIMIT = 1_800_000

_stop = threading.Event()


def connect():
    import psycopg
    from psycopg.rows import dict_row
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn or not dsn.startswith(("postgres://", "postgresql://")):
        raise RuntimeError("Worker cần DATABASE_URL PostgreSQL bí mật.")
    return psycopg.connect(dsn, row_factory=dict_row, connect_timeout=12)


def claim_one(worker_name):
    """Atomically acquire a task across multiple workers via SKIP LOCKED."""
    query = """
    with candidate as (
      select id from public.lmt_durable_jobs
      where (
        (status in ('queued','retry_wait') and retry_after <= now())
        or (status = 'running' and lease_expires_at < now())
      ) and attempts < max_attempts
      order by created_at
      for update skip locked
      limit 1
    )
    update public.lmt_durable_jobs as job
    set status='running', lease_owner=%s, lease_token=gen_random_uuid(),
        lease_expires_at=now() + interval '180 seconds',
        attempts=attempts+1, error='',
        updated_at=now(), stage='Worker đang nhận tác vụ'
    from candidate where job.id=candidate.id
    returning job.id,job.session_id,job.user_id,job.kind,job.snapshot,
       job.encrypted_keys,job.result,job.attempts,job.max_attempts,
       job.lease_token,job.progress
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (worker_name,))
            return cur.fetchone()


def heartbeat_worker(worker_name):
    with connect() as conn:
        conn.execute("""
        insert into public.lmt_worker_health(name,last_seen,version)
        values (%s,now(),'1')
        on conflict(name) do update set last_seen=now(),version='1'
        """, (worker_name,))


def touch_lease(job):
    with connect() as conn:
        result = conn.execute("""
        update public.lmt_durable_jobs
        set lease_expires_at=now() + interval '180 seconds',updated_at=now()
        where id=%s and lease_token=%s and status='running'
        returning id
        """, (job["id"], job["lease_token"])).fetchone()
        return bool(result)


def _sanitize_message(message, secrets):
    cleaned = str(message)
    for secret in secrets.values():
        if isinstance(secret, str) and secret:
            cleaned = cleaned.replace(secret, "[KEY ĐÃ ẨN]")
    return cleaned[:700]


class LeaseProgress:
    """Checkpoint every successful field and percent in durable PostgreSQL."""

    def __init__(self, job, credentials):
        self.job = job
        self.credentials = credentials
        self.inner = JobProgress()
        self.cancelled = threading.Event()
        self.result = dict(job.get("result") or {})
        initial = int(job.get("progress") or 0)
        if initial:
            self.inner.update(initial, "Đã nối lại từ checkpoint")

    def check_cancelled(self):
        self.inner.check_cancelled()
        if self.cancelled.is_set() or _stop.is_set():
            raise RuntimeError("Tác vụ bị dừng hoặc mất quyền sở hữu lease.")

    def update(self, percentage, stage):
        self.check_cancelled()
        self.inner.update(percentage, stage)
        progress, description = self.inner.snapshot()
        self._checkpoint(progress=progress, stage=description)

    def publish(self, field, value):
        self.check_cancelled()
        # Keep only known public result material, never include API keys.
        if field in ("api_key", "image_api_key", "supadata_key", "encrypted_keys"):
            raise ValueError("Không thể ghi API key vào checkpoint.")
        self.inner.publish(field, value)
        self.result[field] = value
        self._checkpoint(field=field, value=value)

    def partial_result(self):
        return dict(self.result)

    def _checkpoint(self, progress=None, stage=None, field=None, value=None):
        # Field is passed separately so the entire intermediate result isn't
        # re-uploaded on every progress update.
        result_blob = json.dumps({field: value}, ensure_ascii=False) if field else None
        if result_blob is not None and len(result_blob) > FIELDS_LIMIT:
            raise ValueError("Checkpoint quá lớn để lưu an toàn.")
        with connect() as conn:
            if field:
                row = conn.execute("""
                update public.lmt_durable_jobs
                set result = result || %s::jsonb,
                    updated_at=now()
                where id=%s and lease_token=%s and status='running'
                returning id
                """, (result_blob, self.job["id"], self.job["lease_token"])).fetchone()
            else:
                row = conn.execute("""
                update public.lmt_durable_jobs
                set progress=greatest(progress,%s),
                    stage=%s,updated_at=now()
                where id=%s and lease_token=%s and status='running'
                returning id
                """, (max(0,min(100,int(progress or 0))),str(stage)[:140],
                      self.job["id"],self.job["lease_token"])).fetchone()
        if not row:
            self.cancelled.set()
            raise RuntimeError("Worker mất lease của tác vụ.")


def _renew_until_stopped(job, progress, stopper):
    while not stopper.wait(HEARTBEAT_SECONDS):
        try:
            if not touch_lease(job):
                progress.cancelled.set()
                return
        except Exception:
            LOG.exception("Heartbeat lease failed for %s", job["id"])
            progress.cancelled.set()
            return


def _image_sink_for(job):
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not service_key or not url:
        return None
    import requests
    from character_images import filename_part
    owner, sid = str(job["user_id"]), str(job["session_id"])

    def save_image(name, content):
        safe_name = filename_part(name) + ".png"
        storage_path = f"{owner}/{sid}/{safe_name}"
        endpoint = f"{url}/storage/v1/object/lmt-character-images/{storage_path}"
        response = requests.post(
            endpoint,
            headers={
                "apikey": service_key,
                "Authorization": "Bearer " + service_key,
                "Content-Type": "image/png", "x-upsert": "true",
            },
            data=content, timeout=120,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Không thể lưu ảnh nhân vật vào Storage (HTTP {response.status_code})."
            )
        return storage_path
    return save_image


def build_snapshot(job):
    """Unseal per-job API keys only inside the private worker process."""
    encrypted = job.get("encrypted_keys")
    if not encrypted:
        raise ValueError("Tác vụ thiếu khóa API được mã hóa.")
    encryption_key = os.environ.get("SESSION_ENCRYPTION_KEY", "").strip()
    if not encryption_key:
        raise RuntimeError("Worker chưa cấu hình SESSION_ENCRYPTION_KEY.")
    keys = json.loads(Fernet(encryption_key.encode()).decrypt(
        encrypted.encode("ascii")
    ).decode("utf-8"))
    snapshot = dict(job["snapshot"])
    snapshot["api_key"] = keys["api_key"]
    if job["kind"] == "full":
        snapshot["supadata_key"] = keys.get("supadata_key", "")
        snapshot["image_api_key"] = keys.get("image_api_key", "")
        snapshot["image_scope"] = "account:" + str(job["user_id"])
        snapshot["image_session_id"] = str(job["session_id"])
        sink = _image_sink_for(job)
        snapshot["auto_character_images"] = bool(
            snapshot.get("auto_character_images") and snapshot["image_api_key"]
            and sink is not None
        )
        if sink is not None:
            snapshot["image_sink"] = sink
        snapshot["resume_fields"] = dict(job.get("result") or {})
    else:
        snapshot["cloud"] = None
        # Existing plan has checkpointed prompts (from prior lease holder).
        if isinstance((job.get("result") or {}).get("video_forms"), str):
            snapshot["existing_plan"] = job["result"]["video_forms"]
    return snapshot, keys


def complete_job(job, progress, result, credentials):
    success = bool(result.get("ok"))
    error = _sanitize_message(result.get("error", ""), credentials)
    lower = error.lower()
    transient = any(k in lower for k in (
        "502", "503", "504", "500", "429", "timeout",
        "gateway", "temporarily", "tạm thời", "quá tải", "rate limit",
        "kết nối", "connection", "retry",
    ))
    attempts = int(job.get("attempts") or 1)
    max_attempts = int(job.get("max_attempts") or 18)
    retryable = not success and transient and attempts < max_attempts
    delay = min(900, 15 * (2 ** min(6, attempts - 1))) if retryable else 0
    if retryable:
        status, stage = "retry_wait", f"⏳ API tạm lỗi; thử lại sau {delay} giây"
    elif success:
        status, stage = "completed", "✅ Hoàn thành và đã lưu trên máy chủ"
    else:
        status, stage = "failed", "⚠️ Dừng do lỗi; kết quả đã có vẫn được lưu"
    # Never write keys to completed/failed records. Failed jobs can be
    # re-submitted from the app with a fresh key after the provider is fixed.
    key_blob = job["encrypted_keys"] if retryable else None
    finished = None if retryable else datetime.now(timezone.utc)
    final_fields = dict(result.get("fields") or {})
    final_fields = {k:v for k,v in final_fields.items()
                    if k not in ("api_key","supadata_key","image_api_key")}
    blob = json.dumps(final_fields, ensure_ascii=False)
    with connect() as conn:
        row = conn.execute("""
        update public.lmt_durable_jobs
        set status=%s, stage=%s, error=%s,
            progress=case when %s then 100 else progress end,
            result=result || %s::jsonb,encrypted_keys=%s,
            retry_after=now()+(%s * interval '1 second'),
            lease_owner=null,lease_token=null,lease_expires_at=null,
            finished_at=%s,updated_at=now()
        where id=%s and lease_token=%s and status='running'
        returning id
        """, (status,stage,error,success,blob,key_blob,delay,finished,
              job["id"],job["lease_token"])).fetchone()
        return bool(row)


def process_one(job):
    snapshot, credentials = build_snapshot(job)
    progress = LeaseProgress(job, credentials)
    waiter = threading.Event()
    heartbeat = threading.Thread(
        target=_renew_until_stopped, args=(job,progress,waiter),
        daemon=True, name="lmt-lease-heartbeat",
    )
    heartbeat.start()
    try:
        if job["kind"] == "full":
            result = run_full_job(snapshot, progress)
        else:
            result = run_video_forms_job(snapshot, progress)
        if progress.cancelled.is_set():
            LOG.warning("Lost lease while processing task %s", job["id"])
            return
        if not complete_job(job, progress, result, credentials):
            LOG.warning("Job %s lost ownership before completion", job["id"])
    except Exception as exc:
        LOG.exception("Unexpected worker failure for %s", job["id"])
        safe = _sanitize_message(exc, credentials)
        complete_job(job, progress, {"ok": False, "error":safe, "fields":{}}, credentials)
    finally:
        waiter.set()
        heartbeat.join(timeout=2)


def run_forever():
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    worker_name = os.environ.get("WORKER_NAME", "") or (
        socket.gethostname()[:48] + "-" + str(os.getpid())
    )
    LOG.info("LMT durable background worker started")
    last_health = 0.0
    while not _stop.is_set():
        try:
            if time.monotonic() - last_health >= HEARTBEAT_SECONDS:
                heartbeat_worker(worker_name)
                last_health = time.monotonic()
            job = claim_one(worker_name)
            if job:
                LOG.info("Accepted job %s (%s)",job["id"],job["kind"])
                process_one(job)
                continue
        except Exception:
            LOG.exception("Polling failed; retrying shortly")
        _stop.wait(POLL_SECONDS)
    LOG.info("Background worker stopped")


def main():
    def handle_signal(_signal, _frame):
        _stop.set()
    signal.signal(signal.SIGTERM,handle_signal)
    signal.signal(signal.SIGINT,handle_signal)
    run_forever()


if __name__=="__main__":
    main()

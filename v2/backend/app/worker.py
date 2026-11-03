"""Run independently: python -m app.worker (from v2/backend).

Leases fence every checkpoint and final commit. A completion locks the session
before the job, like edit/delete/submit, so stale results cannot win a race.
"""
import json
import os
import signal
import socket
import threading
import time
from uuid import uuid4
from psycopg.types.json import Jsonb
from .database import connect
from .settings import get_settings
from .store import unseal, seal

STOP = threading.Event()
PUBLIC_FIELDS = {
    'source','title','caption_language','optimized_script','optimization_review_json',
    'optimization_work_json','translation_parts','translation_complete','translated',
    'character_bible','character_profile','character_profile_json','character_images_manifest',
    'character_images_error','new_title','new_description','seo_tags','metadata','language',
    'video_forms','video_forms_error','repair_memory_json',
}


def clean(value, keys):
    if isinstance(value, str):
        for secret in keys.values():
            if isinstance(secret, str) and secret:
                value = value.replace(secret, '[KEY ĐÃ ẨN]')
        return value
    if isinstance(value, list):
        return [clean(item, keys) for item in value]
    if isinstance(value, dict):
        return {k: clean(v, keys) for k, v in value.items()}
    return value


def heartbeat(name):
    with connect() as conn:
        conn.execute("""insert into public.lmt_v2_worker_health(name,last_seen) values (%s,now())
            on conflict(name) do update set last_seen=now()""", (name,))


def claim(name):
    with connect() as conn:
        conn.execute("""update public.lmt_v2_jobs set status='failed',stage='Đã hết số lần thử',
            encrypted_keys=null,lease_token=null,lease_owner=null,lease_expires_at=null,
            finished_at=now(),updated_at=now()
            where attempts>=max_attempts and ((status='running' and lease_expires_at<now())
                or (status in ('queued','retry_wait') and retry_after<=now()))""")
        return conn.execute("""with candidate as (
            select id from public.lmt_v2_jobs where attempts<max_attempts and session_id is not null and (
                (status in ('queued','retry_wait') and retry_after<=now())
                or (status='running' and lease_expires_at<now()))
            order by created_at for update skip locked limit 1)
            update public.lmt_v2_jobs j set status='running',lease_owner=%s,lease_token=gen_random_uuid(),
                lease_expires_at=now()+interval '180 seconds',attempts=attempts+1,updated_at=now(),error=''
            from candidate c where j.id=c.id returning j.*""", (name,)).fetchone()


class LeaseLost(RuntimeError):
    pass


class Progress:
    def __init__(self, job, keys):
        self.job, self.keys = job, keys
        self.fields = dict(job['result'])
        self.percent = job['progress']
        self.stage = job['stage']
        self.lost = threading.Event()

    def check_cancelled(self):
        if STOP.is_set() or self.lost.is_set():
            raise LeaseLost('Worker dừng hoặc lease đã mất.')
        with connect() as conn:
            row = conn.execute("""select id from public.lmt_v2_jobs where id=%s and user_id=%s
                and lease_token=%s and status='running' and lease_expires_at>now()""",
                (self.job['id'], self.job['user_id'], self.job['lease_token'])).fetchone()
        if not row:
            self.lost.set()
            raise LeaseLost('Tác vụ đã hủy hoặc được worker khác tiếp nhận.')

    def cancel(self):
        self.lost.set()

    def snapshot(self):
        return self.percent, self.stage

    def partial_result(self):
        return dict(self.fields)

    def update(self, percent, stage):
        self.percent = max(self.percent, min(99, int(percent)))
        self.stage = clean(str(stage), self.keys)[:500]
        self._write({})

    def publish(self, field, value):
        if field not in PUBLIC_FIELDS:
            raise ValueError('Trường checkpoint không được phép.')
        value = clean(value, self.keys)
        self._write({field: value})
        self.fields[field] = value

    @staticmethod
    def validate_form_checkpoint(encoded):
        # Match _write's JSON envelope, including Unicode/quote escaping.
        if len(json.dumps({'video_forms': encoded})) > 8_000_000:
            raise ValueError('Checkpoint quá lớn.')

    def _write(self, fields):
        self.check_cancelled()
        if len(json.dumps(fields)) > 8_000_000:
            raise ValueError('Checkpoint quá lớn.')
        with connect() as conn:
            row = conn.execute("""update public.lmt_v2_jobs set result=result || %s,progress=%s,stage=%s,updated_at=now()
                where id=%s and user_id=%s and lease_token=%s and status='running' and lease_expires_at>now() returning id""",
                (Jsonb(fields), self.percent, self.stage, self.job['id'], self.job['user_id'], self.job['lease_token'])).fetchone()
        if not row:
            raise LeaseLost('Không còn lease để ghi checkpoint.')


def renew(job, progress, done):
    while not done.wait(25):
        try:
            heartbeat(job['lease_owner'])
            with connect() as conn:
                row = conn.execute("""update public.lmt_v2_jobs set lease_expires_at=now()+interval '180 seconds'
                    where id=%s and user_id=%s and lease_token=%s and status='running'
                        and lease_expires_at>now() returning id""",
                    (job['id'], job['user_id'], job['lease_token'])).fetchone()
            if not row:
                progress.cancel()
                return
        except Exception:
            progress.cancel()
            return


def completed_fields(kind, fields):
    fields = {k: v for k, v in fields.items() if k in PUBLIC_FIELDS}
    if kind in ('full','translation'):
        fields.update(translation_stale=False,seo_stale=False,character_bible_stale=True,video_forms_stale=True,character_images_stale=True)
    elif kind == 'seo':
        fields['seo_stale'] = False
    elif kind == 'characters':
        fields.update(character_bible_stale=False,video_forms_stale=True,character_images_stale=True)
    elif kind == 'forms':
        fields.update(video_forms_stale=False,character_bible_stale=False,character_images_stale=True)
    elif kind == 'images':
        fields['character_images_stale'] = False
    return fields


def finish(job, progress, result):
    """Exactly-once application with a session revision guard, one transaction."""
    fields = clean({**progress.partial_result(), **result.get('fields', {})}, progress.keys)
    fields = {k: v for k, v in fields.items() if k in PUBLIC_FIELDS}
    success = bool(result.get('ok'))
    error = clean(str(result.get('error', '')), progress.keys)[:700]
    transient = not success and any(x in error.lower() for x in ('502','503','504','timeout','temporarily','connection','kết nối','tạm thời'))
    retry = transient and job['attempts'] < job['max_attempts']
    state = 'completed' if success else ('retry_wait' if retry else 'failed')
    with connect() as conn:
        session = conn.execute('select revision from public.lmt_v2_sessions where id=%s and user_id=%s for update', (job['session_id'], job['user_id'])).fetchone()
        current = conn.execute("""select id from public.lmt_v2_jobs where id=%s and user_id=%s and status='running'
            and lease_token=%s and lease_expires_at>now() for update""", (job['id'], job['user_id'], job['lease_token'])).fetchone()
        if not current:
            return False
        if not session or session['revision'] != job['input_revision']:
            conn.execute("""update public.lmt_v2_jobs set status='cancelled',stage='Đầu vào đã thay đổi',
                encrypted_keys=null,lease_token=null,lease_owner=null,lease_expires_at=null,finished_at=now()
                where id=%s and user_id=%s""", (job['id'], job['user_id']))
            return False
        conn.execute("""update public.lmt_v2_jobs set status=%s,result=%s,error=%s,
            stage=%s,progress=case when %s then 100 else progress end,
            encrypted_keys=%s,lease_token=null,lease_owner=null,lease_expires_at=null,
            retry_after=now()+(%s*interval '1 second'),
            finished_at=case when %s then null else now() end,updated_at=now()
            where id=%s and user_id=%s""",
            (state, Jsonb(fields), error, 'Hoàn thành và đã lưu' if success else ('Đang chờ thử lại' if retry else 'Lỗi; checkpoint được giữ'),
             success, job['encrypted_keys'] if retry else None, min(900,15*2**min(job['attempts'],6)), retry, job['id'], job['user_id']))
        if success:
            conn.execute("""update public.lmt_v2_sessions set data=data || %s,revision=revision+1,
                status='completed',updated_at=now() where id=%s and user_id=%s and revision=%s""",
                (Jsonb(completed_fields(job['job_type'], fields)), job['session_id'], job['user_id'], job['input_revision']))
        else:
            conn.execute("update public.lmt_v2_sessions set status=%s,updated_at=now() where id=%s and user_id=%s", ('queued' if retry else 'failed', job['session_id'], job['user_id']))
    return True


def image_sink(job):
    from .engine import ROOT
    from character_images import filename_part
    import requests
    settings = get_settings()
    if not settings.supabase_service_role_key:
        return None
    def save(name, content):
        path = f"{job['user_id']}/{job['session_id']}/{filename_part(name)}-{job['id']}.png"
        r = requests.post(settings.supabase_url.rstrip('/')+'/storage/v1/object/lmt-character-images/'+path,
            headers={'apikey':settings.supabase_service_role_key,'Authorization':'Bearer '+settings.supabase_service_role_key,
                     'Content-Type':'image/png','x-upsert':'true'}, data=content, timeout=120)
        if r.status_code not in (200,201):
            raise RuntimeError(f'Không lưu được ảnh (HTTP {r.status_code}).')
        return path
    return save


def process(job):
    keys = {}
    progress = Progress(job, keys)
    done = threading.Event()
    thread = threading.Thread(target=renew, args=(job,progress,done), daemon=True)
    thread.start()
    try:
        keys = unseal(job['encrypted_keys'])
        progress.keys = keys
        from .engine import execute
        snapshot = dict(job['input'], **keys, resume_fields=progress.partial_result())
        result = execute(job['job_type'], snapshot, progress, image_sink(job))
        if not STOP.is_set() and not progress.lost.is_set():
            finish(job, progress, result)
    except LeaseLost:
        pass
    except Exception:
        # Provider error bodies/DSNs may contain secrets. The legacy engines
        # return redacted user-facing failures; unexpected exceptions are generic.
        if not STOP.is_set() and not progress.lost.is_set():
            finish(job, progress, dict(ok=False, error='Tác vụ lỗi; checkpoint đã giữ. Kiểm tra cấu hình máy chủ.', fields={}))
    finally:
        done.set()
        thread.join(timeout=2)


def main():
    # Validate key and schema BEFORE advertising a healthy worker.
    seal({})
    with connect() as conn:
        conn.execute('select input_revision,request_id from public.lmt_v2_jobs limit 0')
    name = socket.gethostname()+'-'+str(uuid4())[:8]
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig, lambda *_: STOP.set())
    while not STOP.is_set():
        try:
            heartbeat(name)
            job = claim(name)
            if job:
                process(job)
            else:
                STOP.wait(5)
        except Exception:
            # Do not log SQL/connection exceptions containing server credentials.
            print('Worker: kết nối tạm gián đoạn; đang chờ khôi phục.', flush=True)
            STOP.wait(5)

if __name__ == '__main__':
    main()

"""Atomic owner-scoped persistence; completed jobs apply exactly once."""
import json
from uuid import uuid4
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from .database import connect
from .settings import get_settings
from .legacy_migration import inspect_legacy_state, ALLOWED_EXACT, ALLOWED_PREFIXES

ACTIVE = ('queued', 'running', 'retry_wait')
JOB_PUBLIC = 'id,session_id,job_type,status,progress,stage,attempts,max_attempts,error,created_at,updated_at,input_revision'


def seal(value):
    try:
        return Fernet(get_settings().session_encryption_key.encode()).encrypt(
            json.dumps(value, ensure_ascii=False).encode()).decode()
    except (ValueError, UnicodeError):
        raise HTTPException(503, 'Khóa mã hóa máy chủ chưa hợp lệ.') from None


def unseal(value):
    if not value:
        return {}
    try:
        return json.loads(Fernet(get_settings().session_encryption_key.encode()).decrypt(value.encode()))
    except (InvalidToken, ValueError, UnicodeError):
        raise HTTPException(503, 'Không giải mã được cấu hình; kiểm tra khóa Fernet V1.') from None


def owned_session(conn, owner, sid, lock=False):
    row = conn.execute('select * from public.lmt_v2_sessions where id=%s and user_id=%s' +
                       (' for update' if lock else ''), (sid, owner)).fetchone()
    if not row:
        raise HTTPException(404, 'Không tìm thấy phiên.')
    return row


def config_row(conn, owner):
    return conn.execute('select encrypted_config,settings_version from public.lmt_v2_user_settings where user_id=%s', (owner,)).fetchone()


def config_values(conn, owner):
    row = config_row(conn, owner)
    return unseal(row['encrypted_config']) if row else {}


def public_config(conn, owner):
    row = config_row(conn, owner)
    values = unseal(row['encrypted_config']) if row else {}
    from .engine import migrate_claude_settings, migrate_free_provider_settings
    values = dict(values)
    migrate_claude_settings(values)
    migrate_free_provider_settings(values)
    safe = {k: v for k, v in values.items() if not is_secret(k)}
    return dict(values=safe, configured_keys=[k for k, v in values.items() if is_secret(k) and v],
                version=row['settings_version'] if row else 0)


def is_secret(key):
    return key.startswith('api_key_') or key in ('image_api_key_input', 'supadata_api_key_input')


def save_config(owner, values, version):
    for key, value in values.items():
        if not (key in ALLOWED_EXACT or any(key.startswith(p) for p in ALLOWED_PREFIXES)) or len(value) >= 10000:
            raise HTTPException(422, 'Thiết lập API không hợp lệ.')
    with connect() as conn:
        # Also serializes first insert; two browser tabs cannot silently lose keys.
        conn.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))', (str(owner),))
        row = config_row(conn, owner)
        if version != (row['settings_version'] if row else 0):
            raise HTTPException(409, 'Cấu hình đã thay đổi ở nơi khác. Hãy tải lại.')
        config = unseal(row['encrypted_config']) if row else {}
        config.update(values)
        encrypted = seal(config)
        conn.execute('''insert into public.lmt_v2_user_settings(user_id,encrypted_config,settings_version)
            values (%s,%s,1) on conflict(user_id) do update
            set encrypted_config=excluded.encrypted_config,settings_version=lmt_v2_user_settings.settings_version+1,updated_at=now()''', (owner, encrypted))
        return public_config(conn, owner)


def cancel_active(conn, owner, sid):
    conn.execute('''update public.lmt_v2_jobs set status='cancelled',stage='Đã hủy',encrypted_keys=null,
        lease_token=null,lease_owner=null,lease_expires_at=null,finished_at=now(),updated_at=now()
        where user_id=%s and session_id=%s and status=any(%s)''', (owner, sid, list(ACTIVE)))


def save_session(owner, sid, body):
    values = body.model_dump(exclude={'revision', 'name'})
    with connect() as conn:
        row = owned_session(conn, owner, sid, True)
        if row['revision'] != body.revision:
            raise HTTPException(409, 'Phiên đã có kết quả mới. Hãy tải lại trước khi lưu.')
        old = row['data']
        changed_source = any(values.get(k, '') != old.get(k, '') for k in ('source', 'url')) or values['language'] != old.get('language', 'Tiếng Việt')
        changed_translation = changed_source or values['translated'] != old.get('translated', '')
        changed_style = values['style'] != old.get('style', '')
        if changed_source:
            values['translation_stale'] = True
        elif values['translated'] != old.get('translated', ''):
            values['translation_stale'] = False
        if changed_translation:
            values.update(seo_stale=True, character_bible_stale=True, video_forms_stale=True, character_images_stale=True)
        elif changed_style:
            values.update(character_bible_stale=True, video_forms_stale=True, character_images_stale=True)
        if any(values.get(k) != old.get(k) for k in ('title','description')):
            values['seo_stale'] = True
        cancel_active(conn, owner, sid)
        return conn.execute('''update public.lmt_v2_sessions set name=%s,data=data || %s,
            revision=revision+1,status='draft',updated_at=now() where id=%s and user_id=%s returning *''',
            (body.name, Jsonb(values), sid, owner)).fetchone()


def import_legacy(owner):
    with connect() as conn:
        conn.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))', (str(owner),))
        row = conn.execute('select payload,encrypted_config,updated_at from public.youtube_studio_state where user_id=%s for share', (owner,)).fetchone()
        if not row:
            return dict(imported=0, preserved_existing=0)
        report = inspect_legacy_state(row['payload'], row['encrypted_config'], get_settings().session_encryption_key)
        if not report['ready_for_import']:
            raise HTTPException(409, dict(message='Dữ liệu V1 chưa đạt kiểm tra.', errors=report['errors']))
        # Raw input and ciphertext are preserved losslessly in the same transaction.
        imported = conn.execute('''insert into public.lmt_v2_legacy_imports
            (user_id,source_updated_at,source_payload_sha256,source_config_sha256,raw_payload,encrypted_config,validation_report,status)
            values (%s,%s,%s,%s,%s,%s,%s,'ready')
            on conflict(user_id,source_payload_sha256,source_config_sha256) do update set validation_report=excluded.validation_report returning id''',
            (owner, row['updated_at'], report['legacy_payload_sha256'], report['legacy_encrypted_config_sha256'],
             Jsonb(row['payload']), row['encrypted_config'] or '', Jsonb(report))).fetchone()
        count = 0
        for legacy_id, data in row['payload']['workspaces'].items():
            status = 'interrupted' if data.get('job_state') == 'running' else ('completed' if data.get('processed') else 'draft')
            result = conn.execute('''insert into public.lmt_v2_sessions(user_id,legacy_session_id,name,status,data)
                values (%s,%s,%s,%s,%s) on conflict(user_id,legacy_session_id) where legacy_session_id is not null
                do nothing returning id''', (owner, legacy_id, str(data.get('name') or 'Phiên V1')[:200], status, Jsonb(data))).fetchone()
            count += bool(result)
        if row['encrypted_config']:
            conn.execute('''insert into public.lmt_v2_user_settings(user_id,encrypted_config) values (%s,%s)
                on conflict(user_id) do nothing''', (owner, row['encrypted_config']))
        conn.execute("update public.lmt_v2_legacy_imports set status='imported',imported_at=now() where id=%s and user_id=%s", (imported['id'], owner))
        return dict(imported=count, preserved_existing=report['session_count']-count,
                    source_sha256=report['legacy_payload_sha256'], warnings=report['warnings'])


def enqueue(owner, sid, body):
    from .engine import snapshot_for
    if body.kind not in ('full','translation','seo'):raise HTTPException(422,'Chức năng này đã bỏ khỏi V2.')
    with connect() as conn:
        session = owned_session(conn, owner, sid, True)
        prior = conn.execute(f'select {JOB_PUBLIC} from public.lmt_v2_jobs where user_id=%s and request_id=%s', (owner, body.request_id)).fetchone()
        if prior:
            if str(prior['session_id']) != str(sid) or prior['job_type'] != body.kind:
                raise HTTPException(409, 'Mã yêu cầu đã được dùng cho tác vụ khác.')
            return prior
        if session['revision'] != body.revision:
            raise HTTPException(409, 'Phiên đã thay đổi. Hãy tải lại.')
        if conn.execute('select id from public.lmt_v2_jobs where user_id=%s and session_id=%s and status=any(%s)',
                        (owner, sid, list(ACTIVE))).fetchone():
            raise HTTPException(409, 'Phiên đang có tác vụ. Hãy chờ hoặc hủy trước.')
        if not conn.execute("select name from public.lmt_v2_worker_health where last_seen > now()-interval '150 seconds' limit 1").fetchone():
            raise HTTPException(503, 'Worker độc lập chưa sẵn sàng. Chưa giao tác vụ hoặc gọi API tính phí.')
        data = dict(session['data'])
        config = config_values(conn, owner)
        try:
            snapshot = snapshot_for({k: v for k, v in data.items() if k in {
                'source','url','title','description','language','style','translated',
                'duration_seconds'}}, config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        snapshot.setdefault('language', 'Tiếng Việt')
        keys = {key: snapshot.pop(key) for key in ('api_key','supadata_key','image_api_key')}
        snapshot['uploaded_source'] = data.get('source', '')
        conn.execute("update public.lmt_v2_sessions set status='queued',updated_at=now() where id=%s and user_id=%s", (sid, owner))
        return conn.execute(f'''insert into public.lmt_v2_jobs
            (user_id,session_id,job_type,input,encrypted_keys,input_revision,request_id)
            values (%s,%s,%s,%s,%s,%s,%s) returning {JOB_PUBLIC}''',
            (owner, sid, body.kind, Jsonb(snapshot), seal(keys), session['revision'], body.request_id)).fetchone()


def retry_job(owner, jid):
    with connect() as conn:
        prior = conn.execute('select session_id from public.lmt_v2_jobs where id=%s and user_id=%s', (jid, owner)).fetchone()
        if not prior:
            raise HTTPException(404, 'Không tìm thấy tác vụ.')
        session = owned_session(conn, owner, prior['session_id'], True)
        job = conn.execute('select * from public.lmt_v2_jobs where id=%s and user_id=%s for update', (jid, owner)).fetchone()
        if job['job_type'] not in ('full','translation','seo'):raise HTTPException(422,'Chức năng này đã bỏ khỏi V2.')
        if job['status'] != 'failed' or job['input_revision'] != session['revision']:
            raise HTTPException(409, 'Chỉ tiếp tục job lỗi khi đầu vào chưa thay đổi; nếu đã sửa hãy tạo job mới.')
        if conn.execute('select id from public.lmt_v2_jobs where user_id=%s and session_id=%s and status=any(%s)',
                        (owner, session['id'], list(ACTIVE))).fetchone():
            raise HTTPException(409, 'Phiên đang có tác vụ khác.')
        from .engine import snapshot_for
        try:
            config = dict(config_values(conn, owner))
            config['api_provider'] = job['input']['provider']
            snapshot = snapshot_for(job['input'], config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        # Keep immutable model/base/input on resume; refresh keys only.
        keys = {key: snapshot[key] for key in ('api_key','supadata_key','image_api_key')}
        conn.execute("update public.lmt_v2_sessions set status='queued' where id=%s and user_id=%s", (session['id'], owner))
        return conn.execute(f'''update public.lmt_v2_jobs set status='queued',attempts=0,encrypted_keys=%s,
            retry_after=now(),finished_at=null,error='',stage='Tiếp tục từ checkpoint',updated_at=now()
            where id=%s and user_id=%s returning {JOB_PUBLIC}''', (seal(keys), jid, owner)).fetchone()

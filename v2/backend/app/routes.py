import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from psycopg.types.json import Jsonb
from .auth import require_user, AuthenticatedUser
from .contracts import SessionInput, SessionEdit, JobInput, SettingsInput
from .database import connect
from . import store
from .settings import get_settings

router = APIRouter(prefix='/v1')

@router.get('/sessions')
def list_sessions(user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        return conn.execute('''select id,name,status,revision,legacy_session_id,updated_at
            from public.lmt_v2_sessions where user_id=%s order by updated_at desc limit 150''', (user.id,)).fetchall()

@router.post('/sessions', status_code=201)
def create_session(body: SessionInput, user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        conn.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))', (user.id,))
        count = conn.execute('select count(*) as n from public.lmt_v2_sessions where user_id=%s', (user.id,)).fetchone()['n']
        if count >= 150:
            raise HTTPException(409, 'Đã đạt giới hạn 150 phiên.')
        return conn.execute('''insert into public.lmt_v2_sessions(user_id,name,data) values (%s,%s,%s) returning *''',
                            (user.id, body.name, Jsonb(body.model_dump(exclude={'name'})))).fetchone()

@router.delete('/sessions', status_code=204)
def delete_all_sessions(user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        # Same owner lock as creation; row locks serialize edits and job creation.
        conn.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))', (user.id,))
        rows = conn.execute('select id from public.lmt_v2_sessions where user_id=%s order by id for update',
                            (user.id,)).fetchall()
        for row in rows:
            store.cancel_active(conn, user.id, row['id'])
        conn.execute('delete from public.lmt_v2_sessions where user_id=%s', (user.id,))
    return Response(status_code=204)

@router.get('/sessions/{sid}')
def get_session(sid: UUID, view: str = "", user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        row = store.owned_session(conn, user.id, sid)
        return _studio_session(row) if view == "studio" else row

@router.put('/sessions/{sid}')
def update_session(sid: UUID, body: SessionEdit, user: AuthenticatedUser = Depends(require_user)):
    return store.save_session(user.id, sid, body)

@router.delete('/sessions/{sid}', status_code=204)
def delete_session(sid: UUID, user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        store.owned_session(conn, user.id, sid, True)
        store.cancel_active(conn, user.id, sid)
        conn.execute('delete from public.lmt_v2_sessions where id=%s and user_id=%s', (sid, user.id))
    # Images are retained for rollback; deleted-session jobs cannot commit or
    # start another billable request after their lease cancellation is observed.
    return Response(status_code=204)

@router.get('/providers')
def providers(user: AuthenticatedUser = Depends(require_user)):
    from .engine import PROVIDERS
    return {k: {n: v for n, v in cfg.items() if n != 'secret'} for k, cfg in PROVIDERS.items()}

@router.get('/settings')
def read_settings(user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        return store.public_config(conn, user.id)

@router.put('/settings')
def write_settings(body: SettingsInput, user: AuthenticatedUser = Depends(require_user)):
    return store.save_config(user.id, body.values, body.version)

@router.post('/providers/test')
def test_provider(user: AuthenticatedUser = Depends(require_user)):
    from .engine import provider_snapshot, request_text
    with connect() as conn:
        config = store.config_values(conn, user.id)
    try:
        snapshot = provider_snapshot(config)
        request_text(snapshot, 'Reply with OK only.')
        return {'ok': True}
    except Exception:
        raise HTTPException(422, 'Không kết nối được API. Kiểm tra key, Base URL, model hoặc hạn mức.') from None

@router.post('/providers/models')
def provider_models(user: AuthenticatedUser = Depends(require_user)):
    from .engine import provider_snapshot, list_models
    with connect() as conn:
        config = store.config_values(conn, user.id)
    try:
        s = provider_snapshot(config)
        return list_models(s['provider'], s['base_url'], s['api_key'],
                           api_format=s['api_format'], auth_mode=s['auth_mode'])
    except Exception:
        raise HTTPException(422, 'API không trả danh sách model. Bạn vẫn có thể nhập model thủ công.') from None

@router.post('/sessions/{sid}/jobs', status_code=202)
def submit_job(sid: UUID, body: JobInput, user: AuthenticatedUser = Depends(require_user)):
    return store.enqueue(user.id, sid, body)

@router.get('/jobs')
def jobs(user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        # Keep the latest result for every session and every active job visible,
        # even when one busy session has filled the recent history window.
        return _dashboard_jobs(conn, user.id)


def _dashboard_jobs(conn, owner):
    return conn.execute(f'''with owned as (
                select {store.JOB_PUBLIC} from public.lmt_v2_jobs where user_id=%s
            ), latest as (
                select distinct on (session_id) id from owned where session_id is not null
                order by session_id,created_at desc,id desc
            ) select * from owned where status in ('queued','running','retry_wait')
                or id in (select id from latest)
                or id in (select id from owned order by created_at desc,id desc limit 150)
            order by created_at desc,id desc''', (owner,)).fetchall()

@router.post('/jobs/{jid}/cancel', status_code=204)
def cancel_job(jid: UUID, user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        row = conn.execute('select session_id from public.lmt_v2_jobs where id=%s and user_id=%s', (jid, user.id)).fetchone()
        if not row:
            raise HTTPException(404, 'Không tìm thấy tác vụ.')
        if row['session_id']:
            store.owned_session(conn, user.id, row['session_id'], True)
            store.cancel_active(conn, user.id, row['session_id'])
            conn.execute("update public.lmt_v2_sessions set status='interrupted' where id=%s and user_id=%s and status in ('processing','queued')", (row['session_id'], user.id))
    return Response(status_code=204)

@router.post('/jobs/{jid}/retry', status_code=202)
def retry_job(jid: UUID, user: AuthenticatedUser = Depends(require_user)):
    return store.retry_job(user.id, jid)

@router.get('/worker')
def worker_status(user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        row = conn.execute("select max(last_seen) as last_seen,coalesce(bool_or(last_seen > now()-interval '150 seconds'),false) as healthy from public.lmt_v2_worker_health").fetchone()
        return row

def _studio_session(row):
    # Visual planning/checkpoints remain saved server-side and in exports.
    keys = {'url', 'source', 'title', 'description', 'language', 'style', 'duration_seconds',
            'tts_text', 'translated', 'new_title', 'new_description', 'seo_tags', 'translation_stale', 'seo_stale'}
    return {**row, 'data': {k: v for k, v in row['data'].items() if k in keys}}


def _selected_checkpoint(conn, owner, sid, revision):
    # Project only safe, small diagnostics and the selected job's reviewed narration.
    # The latest job wins even if an older run has a usable translation.
    return conn.execute("""select j.id as job_id,j.session_id,j.input_revision,
        case when j.job_type in ('full','translation')
            and j.result->>'translation_complete'='true'
            then j.result->>'translated' else null end as translated,
        case when j.result->>'translation_complete'='true' then j.result->>'tts_text' else null end as tts_text,
        j.result->>'new_title' as new_title, j.result->>'new_description' as new_description,
        j.result->>'seo_tags' as seo_tags, j.result->'processing_metrics' as metrics
        from public.lmt_v2_jobs j
        where j.id=(select id from public.lmt_v2_jobs where user_id=%s and session_id=%s
                    order by created_at desc,id desc limit 1)
            and j.user_id=%s and j.session_id=%s
            and (j.input_revision=%s or (j.status='completed' and j.input_revision+1=%s))
            and j.status in ('running','retry_wait','failed','completed')""",
        (owner,sid,owner,sid,revision,revision)).fetchone()


@router.get('/dashboard')
def dashboard(sid: UUID | None = None, revision: int = -1,
              user: AuthenticatedUser = Depends(require_user)):
    # One authenticated HTTP request and one DB connection per refresh.
    with connect() as conn:
        sessions = conn.execute('select id,name,status,revision,legacy_session_id,updated_at from public.lmt_v2_sessions where user_id=%s order by updated_at desc limit 150', (user.id,)).fetchall()
        queue = _dashboard_jobs(conn, user.id)
        worker = conn.execute("select coalesce(bool_or(last_seen > now()-interval '150 seconds'),false) as healthy from public.lmt_v2_worker_health").fetchone()
        selected = None
        checkpoint = None
        if sid is not None:
            current = next((row for row in sessions if str(row['id']) == str(sid)), None)
            if current:
                checkpoint = _selected_checkpoint(conn,user.id,sid,current['revision'])
            if current and current['revision'] != revision:
                selected = _studio_session(store.owned_session(conn, user.id, sid))
        return dict(sessions=sessions, jobs=queue, healthy=worker['healthy'], selected=selected, checkpoint=checkpoint)

@router.get('/sessions/{sid}/export')
def export(sid: UUID, format: str = 'json', user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        session = store.owned_session(conn, user.id, sid)
    if format == 'txt':
        content=str(session['data'].get('translated') or '')
        if not content.strip():raise HTTPException(422,'Phiên chưa có bản dịch.')
        media, ext='text/plain; charset=utf-8','txt'
    elif format=='json':
        content, media, ext = json.dumps(session, ensure_ascii=False, default=str, indent=2), 'application/json', 'json'
    else:raise HTTPException(422,'Chỉ xuất TXT bản dịch hoặc JSON phiên.')
    return Response(content, media_type=media, headers={'Content-Disposition': f'attachment; filename="lmt-{sid}.{ext}"'})

from .contracts import ArtifactEdit
@router.put('/sessions/{sid}/artifact')
def edit_artifact(sid: UUID, body: ArtifactEdit, user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        row = store.owned_session(conn, user.id, sid, True)
        if row['revision'] != body.revision:
            raise HTTPException(409, 'Phiên đã thay đổi. Hãy tải lại trước khi sửa.')
        if body.field == 'new_title' and len(body.value)>100:
            raise HTTPException(422, 'Tiêu đề YouTube tối đa 100 ký tự.')
        fields={body.field:body.value}
        fields['metadata']='\n\n'.join(body.value if k==body.field else str(row['data'].get(k,'')) for k in ('new_title','new_description','seo_tags'))
        store.cancel_active(conn,user.id,sid)
        return conn.execute('''update public.lmt_v2_sessions set data=data || %s,revision=revision+1,status='draft',updated_at=now()
            where id=%s and user_id=%s returning *''',(Jsonb(fields),sid,user.id)).fetchone()


import json
from uuid import UUID
from urllib.parse import quote
import httpx
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

@router.get('/sessions/{sid}')
def get_session(sid: UUID, user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        return store.owned_session(conn, user.id, sid)

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
        return conn.execute(f'select {store.JOB_PUBLIC} from public.lmt_v2_jobs where user_id=%s order by created_at desc limit 150', (user.id,)).fetchall()

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

@router.post('/migration/legacy/import')
def migrate(user: AuthenticatedUser = Depends(require_user)):
    return store.import_legacy(user.id)

@router.get('/sessions/{sid}/export')
def export(sid: UUID, format: str = 'json', user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        session = store.owned_session(conn, user.id, sid)
    if format == 'txt':
        from .engine import continuous_combined_forms_text
        try:
            text = continuous_combined_forms_text(json.loads(session['data'].get('video_forms') or '{}'))
        except (ValueError, KeyError, TypeError):
            raise HTTPException(422, 'Phiên chưa có form để xuất.') from None
        content, media, ext = text, 'text/plain; charset=utf-8', 'txt'
    else:
        content, media, ext = json.dumps(session, ensure_ascii=False, default=str, indent=2), 'application/json', 'json'
    return Response(content, media_type=media, headers={'Content-Disposition': f'attachment; filename="lmt-{sid}.{ext}"'})

@router.get('/sessions/{sid}/images')
async def images(sid: UUID, user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        row = store.owned_session(conn, user.id, sid)
    try:
        manifest = json.loads(row['data'].get('character_images_manifest') or '[]')
    except (ValueError, TypeError):
        raise HTTPException(422, 'Manifest ảnh chưa hợp lệ.') from None
    settings = get_settings()
    out = []
    async with httpx.AsyncClient(timeout=20) as client:
        for item in manifest[:10]:
            path = item.get('path') or item.get('storage_path') or ''
            # The backend cannot sign arbitrary paths, even for the same user.
            parts = path.split('/')
            expected = {str(sid), row.get('legacy_session_id')}
            if len(parts) != 3 or parts[0] != user.id or parts[1] not in expected or any(p in ('.','..','') for p in parts):
                continue
            response = await client.post(settings.supabase_url.rstrip('/') + '/storage/v1/object/sign/lmt-character-images/' + quote(path, safe='/'),
                headers={'apikey': settings.supabase_publishable_key, 'Authorization': 'Bearer ' + user.access_token}, json={'expiresIn': 300})
            if response.is_success:
                signed = response.json().get('signedURL', '')
                if signed.startswith('/'):
                    out.append(dict(name=item.get('name', parts[-1]), url=settings.supabase_url.rstrip('/') + '/storage/v1' + signed))
    return out

@router.get('/sessions/{sid}/thumbnail')
async def thumbnail(sid: UUID, user: AuthenticatedUser = Depends(require_user)):
    from .engine import ROOT
    from background_jobs import youtube_id
    with connect() as conn:
        row = store.owned_session(conn, user.id, sid)
    vid = youtube_id(row['data'].get('url', ''))
    if not vid:
        raise HTTPException(422, 'Phiên chưa có link YouTube hợp lệ.')
    async with httpx.AsyncClient(timeout=12) as client:
        for quality in ('maxresdefault','sddefault','hqdefault'):
            r = await client.get(f'https://i.ytimg.com/vi/{vid}/{quality}.jpg')
            if r.status_code == 200 and r.headers.get('content-type','').startswith('image/') and len(r.content) <= 10_000_000:
                return Response(r.content, media_type='image/jpeg', headers={'Content-Disposition':f'attachment; filename="{vid}.jpg"','Cache-Control':'private, max-age=3600'})
    raise HTTPException(502, 'Chưa tải được thumbnail gốc.')

@router.get('/sessions/{sid}/images.zip')
async def images_zip(sid: UUID, user: AuthenticatedUser = Depends(require_user)):
    from io import BytesIO
    import zipfile
    from .engine import ROOT
    from character_images import filename_part
    with connect() as conn:
        row = store.owned_session(conn, user.id, sid)
    try:
        manifest = json.loads(row['data'].get('character_images_manifest') or '[]')
    except (ValueError, TypeError):
        raise HTTPException(422, 'Manifest ảnh chưa hợp lệ.') from None
    if not manifest:
        raise HTTPException(422, 'Chưa có ảnh đã lưu.')
    settings = get_settings()
    buffer = BytesIO()
    async with httpx.AsyncClient(timeout=30) as client:
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for index, item in enumerate(manifest[:10], 1):
                path = item.get('path') or item.get('storage_path') or ''
                parts = path.split('/')
                if len(parts) != 3 or parts[0] != user.id or parts[1] not in {str(sid),row.get('legacy_session_id')} or any(p in ('.','..','') for p in parts):
                    raise HTTPException(422, 'Đường dẫn ảnh không thuộc phiên.')
                r = await client.get(settings.supabase_url.rstrip('/')+'/storage/v1/object/authenticated/lmt-character-images/'+quote(path,safe='/'),
                    headers={'apikey':settings.supabase_publishable_key,'Authorization':'Bearer '+user.access_token})
                if not r.is_success or len(r.content)>12*1024*1024 or not r.content.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise HTTPException(502, 'Không tải đủ ảnh; chưa tạo ZIP để tránh thiếu dữ liệu.')
                archive.writestr(f'{index:02d}-{filename_part(item.get("name",parts[-1]))}.png',r.content)
    return Response(buffer.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="lmt-{sid}-characters.zip"'})

from .contracts import ArtifactEdit
@router.put('/sessions/{sid}/artifact')
def edit_artifact(sid: UUID, body: ArtifactEdit, user: AuthenticatedUser = Depends(require_user)):
    with connect() as conn:
        row = store.owned_session(conn, user.id, sid, True)
        if row['revision'] != body.revision:
            raise HTTPException(409, 'Phiên đã thay đổi. Hãy tải lại trước khi sửa.')
        if body.field == 'scene':
            if not body.scene_number or not body.prompt_field:
                raise HTTPException(422, 'Cần chọn cảnh và loại prompt.')
            try:
                plan = json.loads(row['data'].get('video_forms') or '{}')
                scene = next(s for s in plan['scenes'] if s['number']==body.scene_number)
            except (ValueError, KeyError, TypeError, StopIteration):
                raise HTTPException(422, 'Không tìm thấy cảnh.') from None
            scene[body.prompt_field] = body.value
            fields = dict(video_forms=json.dumps(plan, ensure_ascii=False))
        else:
            if body.field == 'new_title' and len(body.value)>100:
                raise HTTPException(422, 'Tiêu đề YouTube tối đa 100 ký tự.')
            fields = {body.field: body.value}
            if body.field == 'character_bible':
                fields.update(character_bible_stale=True,video_forms_stale=True,character_images_stale=True)
            else:
                fields['metadata']='\n\n'.join(body.value if k==body.field else str(row['data'].get(k,'')) for k in ('new_title','new_description','seo_tags'))
        store.cancel_active(conn,user.id,sid)
        return conn.execute('''update public.lmt_v2_sessions set data=data || %s,revision=revision+1,status='draft',updated_at=now()
            where id=%s and user_id=%s returning *''',(Jsonb(fields),sid,user.id)).fetchone()

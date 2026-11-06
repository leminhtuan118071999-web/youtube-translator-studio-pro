import json
from uuid import uuid4
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from app.main import app
from app.auth import require_user, AuthenticatedUser
from app.database import connect
from app.contracts import SessionInput,SessionEdit,JobInput
from app import store, worker
from app.settings import get_settings


def session(owner, data=None):
    with connect() as c:
        return c.execute('insert into public.lmt_v2_sessions(user_id,name,data) values (%s,%s,%s) returning *',
                         (owner,'Test',Jsonb(data or dict(source='Original',language='Tiếng Việt',style='2D',translated='Bản dịch')))).fetchone()


def configured(owner):
    store.save_config(owner, {'api_provider':'OpenAI','api_key_OpenAI':'private-provider-key'},0)
    worker.heartbeat('test-worker')


def submit(owner,s,kind='full',rid=None):
    # Do not depend on public DNS to test queue transactions.
    with patch('app.engine.validate_base_url', return_value='https://api.openai.com/v1'):
        return store.enqueue(owner,s['id'],JobInput(kind=kind,revision=s['revision'],request_id=rid or uuid4()))


def test_import_is_lossless_idempotent_and_does_not_overwrite_v2(db):
    owner,_ = db
    raw = dict(name='V1',source='Text',seo_stale=True,unknown_future_field={'x':[1,2]})
    payload = dict(version=1,workspaces={'a'*32:raw},selected_session='a'*32)
    with connect() as c:
        c.execute('insert into youtube_studio_state(user_id,payload,encrypted_config) values (%s,%s,%s)',(owner,Jsonb(payload),store.seal({'api_provider':'OpenAI','api_key_OpenAI':'secret'})))
    assert store.import_legacy(owner)['imported'] == 1
    with connect() as c:
        row=c.execute('select * from lmt_v2_sessions where user_id=%s',(owner,)).fetchone()
        assert row['data']==raw
        c.execute("update lmt_v2_sessions set data=data || '{\"source\":\"New V2 text\"}' where id=%s",(row['id'],))
    assert store.import_legacy(owner)['preserved_existing']==1
    with connect() as c:
        assert c.execute('select data from lmt_v2_sessions where id=%s',(row['id'],)).fetchone()['data']['source']=='New V2 text'
        assert c.execute('select payload from youtube_studio_state where user_id=%s',(owner,)).fetchone()['payload']==payload
        assert c.execute('select raw_payload from lmt_v2_legacy_imports where user_id=%s',(owner,)).fetchone()['raw_payload']==payload


def test_bad_encryption_rolls_back_all_import_rows(db):
    owner,_=db
    with connect() as c:
        c.execute('insert into youtube_studio_state(user_id,payload,encrypted_config) values (%s,%s,%s)',(owner,Jsonb(dict(version=1,workspaces={'a'*32:{'name':'V1'}})),'wrong ciphertext'))
    with pytest.raises(HTTPException) as e:
        store.import_legacy(owner)
    assert e.value.status_code==409
    with connect() as c:
        assert c.execute('select count(*) as n from lmt_v2_sessions where user_id=%s',(owner,)).fetchone()['n']==0


def test_settings_secret_masking_and_concurrent_update(db):
    owner,_=db
    out=store.save_config(owner,{'api_key_OpenAI':'secret','api_provider':'OpenAI'},0)
    assert 'secret' not in json.dumps(out)
    assert out['configured_keys']==['api_key_OpenAI']
    with pytest.raises(HTTPException) as e:
        store.save_config(owner,{'api_provider':'Groq'},0)
    assert e.value.status_code==409
    with connect() as c:
        assert store.config_values(c,owner)['api_key_OpenAI']=='secret'


def test_same_request_only_creates_one_job_and_keys_are_encrypted(db):
    owner,_=db
    configured(owner); s=session(owner); rid=uuid4()
    a=submit(owner,s,rid=rid); b=submit(owner,s,rid=rid)
    assert a['id']==b['id']
    assert 'encrypted_keys' not in a and 'private-provider-key' not in json.dumps(a,default=str)
    with connect() as c:
        j=c.execute('select * from lmt_v2_jobs where id=%s',(a['id'],)).fetchone()
        assert 'private-provider-key' not in json.dumps(j['input'])
        assert store.unseal(j['encrypted_keys'])['api_key']=='private-provider-key'


def test_second_active_job_is_rejected(db):
    owner,_=db
    configured(owner); s=session(owner); submit(owner,s)
    with pytest.raises(HTTPException) as e:
        submit(owner,s,kind='seo')
    assert e.value.status_code==409


def test_missing_worker_never_enqueues_or_calls_provider(db):
    owner,_=db
    s=session(owner)
    with connect() as c:
        c.execute("update lmt_v2_worker_health set last_seen=now()-interval '1 day'")
    with pytest.raises(HTTPException) as e:
        submit(owner,s)
    assert e.value.status_code==503


def test_completion_applies_once_and_old_job_cannot_overwrite_manual_edit(db):
    owner,_=db
    configured(owner); s=session(owner); submit(owner,s)
    job=worker.claim('test-worker'); p=worker.Progress(job,{'api_key':'private-provider-key'})
    assert worker.finish(job,p,dict(ok=True,fields={'translated':'First result'},error=''))
    assert not worker.finish(job,p,dict(ok=True,fields={'translated':'Old result'},error=''))
    with connect() as c:
        updated=store.owned_session(c,owner,s['id'])
        assert updated['revision']==1 and updated['data']['translated']=='First result'
        assert c.execute('select encrypted_keys from lmt_v2_jobs where id=%s',(job['id'],)).fetchone()['encrypted_keys'] is None
    store.save_session(owner,s['id'],SessionEdit(name='Edited',revision=1,source='Original',translated='Manual edit'))
    assert not worker.finish(job,p,dict(ok=True,fields={'translated':'Old result'}))
    with connect() as c:
        assert store.owned_session(c,owner,s['id'])['data']['translated']=='Manual edit'


def test_edit_cancels_running_lease_and_preserves_stale_booleans(db):
    owner,_=db
    configured(owner); s=session(owner); submit(owner,s)
    job=worker.claim('test-worker'); p=worker.Progress(job,{})
    saved=store.save_session(owner,s['id'],SessionEdit(name='Change',revision=0,source='Changed',translated='Manual'))
    assert saved['data']['seo_stale'] is True
    with pytest.raises(worker.LeaseLost): p.publish('translated','Old')
    assert not worker.finish(job,p,dict(ok=True,fields={'translated':'Old'}))
    with connect() as c:
        assert store.owned_session(c,owner,s['id'])['data']['translated']=='Manual'


def test_expired_lease_resumes_checkpoint_and_fences_previous_worker(db):
    owner,_=db
    configured(owner); s=session(owner); submit(owner,s)
    first=worker.claim('first'); p=worker.Progress(first,{})
    p.publish('optimization_work_json','checkpoint')
    with connect() as c: c.execute("update lmt_v2_jobs set lease_expires_at=now()-interval '1 second' where id=%s",(first['id'],))
    second=worker.claim('second')
    assert first['id']==second['id'] and first['lease_token']!=second['lease_token']
    assert second['result']['optimization_work_json']=='checkpoint'
    with pytest.raises(worker.LeaseLost): p.publish('translated','Late result')
    assert not worker.finish(first,p,dict(ok=True,fields={'translated':'Late'}))


def test_transient_retry_keeps_checkpoint_and_keys(db):
    owner,_=db
    configured(owner); s=session(owner); submit(owner,s)
    job=worker.claim('test-worker'); p=worker.Progress(job,{})
    p.publish('optimization_work_json','part one')
    assert worker.finish(job,p,dict(ok=False,fields={},error='HTTP 503'))
    with connect() as c:
        j=c.execute('select * from lmt_v2_jobs where id=%s',(job['id'],)).fetchone()
        assert j['status']=='retry_wait' and j['encrypted_keys'] and j['result']['optimization_work_json']=='part one'


def test_manual_resume_rejects_changed_input(db):
    owner,_=db
    configured(owner); s=session(owner); job=submit(owner,s)
    with connect() as c:
        c.execute("update lmt_v2_jobs set status='failed' where id=%s",(job['id'],))
        c.execute('update lmt_v2_sessions set revision=revision+1 where id=%s',(s['id'],))
    with pytest.raises(HTTPException) as e: store.retry_job(owner,job['id'])
    assert e.value.status_code==409


def test_wrong_owner_get_edit_delete_submit_cancel_export_are_denied(db):
    owner,other=db
    configured(owner); s=session(owner); job=submit(owner,s)
    app.dependency_overrides[require_user]=lambda: AuthenticatedUser(other,'other@example.com','token')
    try:
        with TestClient(app) as client:
            assert client.get(f"/v1/sessions/{s['id']}").status_code==404
            assert client.delete(f"/v1/sessions/{s['id']}").status_code==404
            assert client.get(f"/v1/sessions/{s['id']}/export").status_code==404
            assert client.post(f"/v1/sessions/{s['id']}/jobs",json=dict(kind='full',revision=0,request_id=str(uuid4()))).status_code==404
            assert client.post(f"/v1/jobs/{job['id']}/cancel").status_code==404
            assert client.get('/v1/sessions').json()==[]
    finally: app.dependency_overrides.clear()


def test_delete_cancels_job_and_prevents_completion(db):
    owner,_=db
    configured(owner); s=session(owner); submit(owner,s)
    j=worker.claim('test-worker'); p=worker.Progress(j,{})
    app.dependency_overrides[require_user]=lambda: AuthenticatedUser(owner,None,'token')
    try:
        with TestClient(app) as client: assert client.delete(f"/v1/sessions/{s['id']}").status_code==204
    finally: app.dependency_overrides.clear()
    assert not worker.finish(j,p,dict(ok=True,fields={'translated':'Should not return'}))
    with connect() as c:
        row=c.execute('select * from lmt_v2_jobs where id=%s',(j['id'],)).fetchone()
        assert row['status']=='cancelled' and row['encrypted_keys'] is None and row['session_id'] is None


def test_rls_direct_read_separates_owners_and_hides_job_ciphertexts(db):
    owner,other=db
    s=session(owner)
    with connect() as c:
        c.execute("select set_config('request.jwt.claim.sub',%s,true)",(other,))
        c.execute('set local role authenticated')
        assert c.execute('select id from lmt_v2_sessions where id=%s',(s['id'],)).fetchall()==[]
    import psycopg
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connect() as c:
            c.execute("select set_config('request.jwt.claim.sub',%s,true)",(owner,))
            c.execute('set local role authenticated')
            c.execute('select encrypted_keys from lmt_v2_jobs')


def test_validation_does_not_echo_new_api_key():
    app.dependency_overrides[require_user]=lambda: AuthenticatedUser(str(uuid4()),None,'token')
    try:
        with TestClient(app) as client:
            response=client.put('/v1/settings',json={'values':{'api_key_OpenAI':['sensitive-new-key']},'version':0})
            assert response.status_code==422 and 'sensitive-new-key' not in response.text
    finally: app.dependency_overrides.clear()


def test_worker_runs_direct_translation_and_parallel_metadata_into_durable_session(db):
    owner,_=db
    configured(owner)
    s=session(owner,dict(source='Nora saved Maisie.',language='English',style='2D',url=''))
    submit(owner,s)
    job=worker.claim('test-worker')
    def provider(p,b,m,k,prompt,**kwargs):
        if prompt.startswith('DIRECT_TRANSLATION'): return '{"text":"Nora saved Maisie.","seo_context":"Nora saved Maisie.","complete":true,"number_readings":[]}'
        if prompt.startswith('FAITHFULNESS_REVIEW'): return '{"ok":true,"issues":[],"source_conflicts":[]}'
        if prompt.startswith(('Summarize','Condense')): return 'Nora saved Maisie.'
        if prompt.startswith('TARGET_METADATA_REVIEW'): return '{"ok":true,"issues":[]}'
        if prompt.startswith('TARGET_METADATA'): return '{"title":"Rescue","description":"Nora saves Maisie.","tags":["rescue"]}'
        raise AssertionError('Unexpected provider call')
    with patch('app.text_pipeline.generate_text',side_effect=provider):
        worker.process(job)
    with connect() as c:
        saved=store.owned_session(c,owner,s['id'])
        assert saved['status']=='completed'
        assert saved['data']['translated']=='Nora saved Maisie.'
        assert saved['data']['new_title']=='Rescue'
        assert saved['data']['translation_stale'] is False
        j=c.execute('select * from lmt_v2_jobs where id=%s',(job['id'],)).fetchone()
        assert j['status']=='completed' and j['progress']==100 and j['encrypted_keys'] is None


def test_final_expired_attempt_is_failed_and_credentials_erased(db):
    owner,_=db
    configured(owner); s=session(owner); j=submit(owner,s)
    with connect() as c:
        c.execute("update lmt_v2_jobs set status='running',attempts=max_attempts,lease_expires_at=now()-interval '1 second' where id=%s",(j['id'],))
    assert worker.claim('test-worker') is None
    with connect() as c:
        row=c.execute('select status,encrypted_keys from lmt_v2_jobs where id=%s',(j['id'],)).fetchone()
        assert row['status']=='failed' and row['encrypted_keys'] is None


def test_stale_session_save_is_rejected_without_cancelling_new_work(db):
    owner,_=db
    configured(owner); s=session(owner)
    with connect() as c: c.execute('update lmt_v2_sessions set revision=1 where id=%s',(s['id'],))
    with pytest.raises(HTTPException) as e: store.save_session(owner,s['id'],SessionEdit(name='Old tab',revision=0))
    assert e.value.status_code==409


def test_unknown_checkpoint_field_cannot_expose_credentials(db):
    owner,_=db
    configured(owner); s=session(owner); submit(owner,s)
    j=worker.claim('test-worker'); p=worker.Progress(j,{'api_key':'secret'})
    with pytest.raises(ValueError): p.publish('api_key','secret')
    p.publish('translated','A provider accidentally echoed secret')
    with connect() as c:
        assert 'secret' not in json.dumps(c.execute('select result from lmt_v2_jobs where id=%s',(j['id'],)).fetchone())


def test_resume_uses_original_providers_key_after_user_switches_provider(db):
    owner,_=db
    configured(owner); s=session(owner); j=submit(owner,s)
    with connect() as c: c.execute("update lmt_v2_jobs set status='failed',encrypted_keys=null where id=%s",(j['id'],))
    store.save_config(owner,dict(api_provider='Groq',api_key_Groq='different-provider-key'),1)
    with patch('app.engine.validate_base_url',return_value='https://api.openai.com/v1'):
        store.retry_job(owner,j['id'])
    with connect() as c:
        row=c.execute('select input,encrypted_keys from lmt_v2_jobs where id=%s',(j['id'],)).fetchone()
        assert row['input']['provider']=='OpenAI'
        assert store.unseal(row['encrypted_keys'])['api_key']=='private-provider-key'


def test_removed_scene_edit_is_rejected_and_legacy_data_preserved(db):
    owner,other=db
    plan=dict(scenes=[dict(number=1,voiceover='Locked narration',start=0,end=8,visual_prompt='Old prompt',image_prompt='Image')])
    s=session(owner,dict(video_forms=json.dumps(plan)))
    app.dependency_overrides[require_user]=lambda: AuthenticatedUser(owner,None,'token')
    try:
        with TestClient(app) as client:
            response=client.put(f"/v1/sessions/{s['id']}/artifact",json=dict(field='scene',scene_number=1,prompt_field='visual_prompt',revision=0,value='New visual'))
            assert response.status_code==422
            with connect() as conn:
                assert json.loads(store.owned_session(conn,owner,s['id'])['data']['video_forms'])==plan
    finally: app.dependency_overrides.clear()


def test_api_rejects_forged_owner_and_no_auth():
    with TestClient(app) as client:
        assert client.get('/v1/sessions').status_code==401
    app.dependency_overrides[require_user]=lambda: AuthenticatedUser(str(uuid4()),None,'token')
    try:
        with TestClient(app) as client:
            response=client.post('/v1/sessions',json=dict(user_id=str(uuid4())))
            assert response.status_code==422
    finally: app.dependency_overrides.clear()


def test_jobs_keep_each_session_latest_and_old_active_jobs_beyond_recent_window(db):
    from app.routes import jobs
    owner, other = db
    older, busy, foreign = session(owner), session(owner), session(other)
    with connect() as c:
        def insert(sid, uid, status, age):
            return c.execute("""insert into lmt_v2_jobs(user_id,session_id,job_type,status,input,input_revision,request_id,created_at)
                values (%s,%s,'seo',%s,'{}',1,%s,now()-(%s * interval '1 minute')) returning id""",
                (uid,sid,status,uuid4(),age)).fetchone()['id']
        latest_older = insert(older['id'], owner, 'completed', 1000)
        old_active = insert(busy['id'], owner, 'running', 999)
        foreign_id = insert(foreign['id'], other, 'running', 0)
        recent = [insert(busy['id'], owner, 'completed', age) for age in range(151)]
    rows = jobs(AuthenticatedUser(id=owner, email='owner@example.com', access_token='test'))
    ids = {row['id'] for row in rows}
    assert latest_older in ids and old_active in ids
    assert recent[0] in ids and foreign_id not in ids
    assert all('encrypted_keys' not in row and 'input' not in row for row in rows)


def test_selected_checkpoint_is_reviewed_owner_scoped_and_revision_fenced(db):
    from app.routes import _selected_checkpoint
    owner,other=db
    configured(owner);s=session(owner);submit(owner,s)
    job=worker.claim('test-worker');p=worker.Progress(job,{})
    p.publish('translated','Reviewed narration')
    p.publish('tts_text','Reviewed AI reading')
    p.publish('processing_metrics',dict(calls=2,phases={}))
    with connect() as c:
        preview=_selected_checkpoint(c,owner,s['id'],s['revision'])
        assert preview['translated'] is None
        assert preview['tts_text'] is None
        assert preview['metrics']['calls']==2
    p.publish('translation_complete',True)
    with connect() as c:
        preview=_selected_checkpoint(c,owner,s['id'],s['revision'])
        assert preview['translated']=='Reviewed narration'
        assert preview['tts_text']=='Reviewed AI reading'
        assert set(preview)=={'job_id','session_id','input_revision','translated','tts_text','source_metadata','new_title','new_description','seo_tags','metrics'}
        assert _selected_checkpoint(c,other,s['id'],s['revision']) is None
        assert _selected_checkpoint(c,owner,s['id'],s['revision']+1) is None
    assert worker.finish(job,p,dict(ok=True,fields={'translated':'Reviewed narration'}))
    with connect() as c:
        assert _selected_checkpoint(c,owner,s['id'],s['revision']+1)['metrics']['calls']==2
    store.save_session(owner,s['id'],SessionEdit(name='Manual',revision=1,source='New input',translated='Manual narration'))
    with connect() as c:
        assert _selected_checkpoint(c,owner,s['id'],2) is None


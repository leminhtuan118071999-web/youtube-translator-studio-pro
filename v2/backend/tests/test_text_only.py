from fastapi.testclient import TestClient
from app.main import app


def test_removed_features_not_registered():
    paths=set(TestClient(app).get('/openapi.json').json()['paths'])
    assert '/v1/migration/legacy/import' not in paths
    assert '/v1/migration/legacy/dry-run' not in paths
    assert '/v1/sessions/{sid}/images' not in paths
    assert '/v1/sessions/{sid}/images.zip' not in paths
    assert '/v1/sessions/{sid}/thumbnail' not in paths


def test_openapi_exposes_only_text_job_kinds():
    schema=TestClient(app).get('/openapi.json').json()
    assert set(schema['components']['schemas']['JobInput']['properties']['kind']['enum'])=={'full','translation','seo'}
    assert set(schema['components']['schemas']['ArtifactEdit']['properties']['field']['enum'])=={'new_title','new_description','seo_tags'}


def test_spoken_translation_round_trips_in_studio_view():
    from app.routes import _studio_session
    row={'data':{'tts_text':'twenty-three','translated':'23'}}
    assert _studio_session(row)['data']==row['data']

def test_txt_export_prefers_spoken_text_and_preserves_old_session_fallback():
    from app.routes import export
    from unittest.mock import patch
    from types import SimpleNamespace
    from uuid import uuid4
    sid=uuid4();user=SimpleNamespace(id=uuid4())
    with patch('app.routes.connect'), patch('app.routes.store.owned_session',return_value={'data':{'translated':'23 minutes','tts_text':'twenty-three minutes'}}):
        assert export(sid,'txt',user).body.decode()=='twenty-three minutes'
    with patch('app.routes.connect'), patch('app.routes.store.owned_session',return_value={'data':{'translated':'23 minutes'}}):
        assert export(sid,'txt',user).body.decode()=='23 minutes'


def test_dashboard_omits_unchanged_checkpoint_and_refreshes_after_job_or_revision_change():
    from app.routes import dashboard
    from unittest.mock import MagicMock, patch
    from types import SimpleNamespace
    from datetime import datetime, timezone, timedelta
    from uuid import uuid4
    sid=uuid4()
    user=SimpleNamespace(id=uuid4())
    session=dict(id=sid,revision=4)
    job=dict(id=uuid4(),session_id=sid,updated_at=datetime.now(timezone.utc))
    checkpoint=dict(translated='Long translation',tts_text='Spoken translation')
    conn=MagicMock()
    conn.execute.return_value.fetchall.return_value=[session]
    conn.execute.return_value.fetchone.return_value={'healthy':True}
    with patch('app.routes.connect') as connect, patch(
            'app.routes._dashboard_jobs',return_value=[job]), patch(
            'app.routes._selected_checkpoint',return_value=checkpoint) as load:
        connect.return_value.__enter__.return_value=conn
        first=dashboard(sid=sid,revision=4,user=user)
        assert first['checkpoint']==checkpoint
        assert first['checkpoint_unchanged'] is False
        load.reset_mock()
        unchanged=dashboard(sid=sid,revision=4,checkpoint_version=first['checkpoint_version'],user=user)
        assert unchanged['checkpoint'] is None
        assert unchanged['checkpoint_unchanged'] is True
        load.assert_not_called()
        job['updated_at']+=timedelta(seconds=1)
        changed=dashboard(sid=sid,revision=4,checkpoint_version=first['checkpoint_version'],user=user)
        assert changed['checkpoint']==checkpoint
        assert changed['checkpoint_version']!=first['checkpoint_version']
        session['revision']=5
        changed_revision=dashboard(sid=sid,revision=5,checkpoint_version=changed['checkpoint_version'],user=user)
        assert changed_revision['checkpoint_unchanged'] is False
        assert changed_revision['checkpoint']==checkpoint

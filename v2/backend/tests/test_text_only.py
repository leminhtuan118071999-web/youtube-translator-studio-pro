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

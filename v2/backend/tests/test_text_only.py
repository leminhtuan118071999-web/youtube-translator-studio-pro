from fastapi.testclient import TestClient
from app.main import app


def test_removed_features_not_registered():
    paths=set(TestClient(app).get('/openapi.json').json()['paths'])
    assert '/v1/migration/legacy/import' not in paths
    assert '/v1/sessions/{sid}/images' not in paths
    assert '/v1/sessions/{sid}/images.zip' not in paths
    assert '/v1/sessions/{sid}/thumbnail' not in paths


def test_openapi_exposes_only_text_job_kinds():
    schema=TestClient(app).get('/openapi.json').json()
    assert set(schema['components']['schemas']['JobInput']['properties']['kind']['enum'])=={'full','translation','seo'}
    assert set(schema['components']['schemas']['ArtifactEdit']['properties']['field']['enum'])=={'new_title','new_description','seo_tags'}

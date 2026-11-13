from unittest.mock import MagicMock, patch
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.auth import require_user, AuthenticatedUser


def test_dashboard_requires_auth():
    assert TestClient(app).get('/v1/dashboard').status_code == 401


def test_dashboard_uses_one_connection_and_skips_unchanged_or_foreign_session():
    sid = uuid4()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [{'id': sid, 'revision': 4}]
    conn.execute.return_value.fetchone.return_value = {'healthy': True}
    app.dependency_overrides[require_user] = lambda: AuthenticatedUser('owner', 'o@example.com', 'test')
    try:
        with patch('app.routes.connect') as connect, patch('app.routes._dashboard_jobs', return_value=[]) as jobs, patch('app.routes.store.owned_session') as owned:
            connect.return_value.__enter__.return_value = conn
            client = TestClient(app)
            for requested in [sid, uuid4()]:
                response = client.get(f'/v1/dashboard?sid={requested}&revision=4')
                assert response.status_code == 200
                assert response.json()['selected'] is None
            owned.assert_not_called()
            assert connect.call_count == 2
            jobs.assert_called_with(conn, 'owner')
            assert conn.execute.call_args_list[0].args[1] == ('owner',)
    finally:
        app.dependency_overrides.clear()


def test_changed_session_has_translation_but_no_heavy_visual_artifacts():
    sid = uuid4()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [{'id': sid, 'revision': 5}]
    conn.execute.return_value.fetchone.return_value = {'healthy': False}
    app.dependency_overrides[require_user] = lambda: AuthenticatedUser('owner', 'o@example.com', 'test')
    original = {'id': sid, 'revision': 5, 'data': {'translated': 'New narration', 'video_forms': 'large', 'optimization_work_json': 'large', 'character_bible': 'large'}}
    try:
        with patch('app.routes.connect') as connect, patch('app.routes._dashboard_jobs', return_value=[]), patch('app.routes.store.owned_session', return_value=original) as owned:
            connect.return_value.__enter__.return_value = conn
            response = TestClient(app).get(f'/v1/dashboard?sid={sid}&revision=4')
            assert response.status_code == 200
            assert response.json()['selected']['data'] == {'translated': 'New narration'}
            owned.assert_called_once_with(conn, 'owner', sid)
            assert 'video_forms' in original['data']
    finally:
        app.dependency_overrides.clear()

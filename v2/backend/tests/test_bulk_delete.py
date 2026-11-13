from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.auth import require_user, AuthenticatedUser


def test_bulk_delete_requires_auth():
    assert TestClient(app).delete('/v1/sessions').status_code == 401


def test_bulk_delete_cancels_only_owned_sessions_in_one_transaction():
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [{'id': 'one'}, {'id': 'two'}]
    app.dependency_overrides[require_user] = lambda: AuthenticatedUser(id='owner', email='owner@example.com', access_token='test-token')
    try:
        with patch('app.routes.connect') as connect, patch('app.routes.store.cancel_active') as cancel:
            connect.return_value.__enter__.return_value = conn
            response = TestClient(app).delete('/v1/sessions')
            assert response.status_code == 204
            assert response.content == b''
            assert [c.args for c in cancel.call_args_list] == [(conn, 'owner', 'one'), (conn, 'owner', 'two')]
            statements = conn.execute.call_args_list
            assert 'for update' in statements[1].args[0]
            assert all(c.args[1] == ('owner',) for c in statements)
            assert statements[-1].args[0] == 'delete from public.lmt_v2_sessions where user_id=%s'
            assert connect.return_value.__exit__.call_args.args == (None, None, None)
    finally:
        app.dependency_overrides.clear()

"""Private server-only connection. API queries bind a Supabase-verified owner.

Privileged connection permits atomic job/session transactions. NEVER expose
this DSN in the frontend. RLS separately protects direct Supabase access.
"""
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from fastapi import HTTPException
from .settings import get_settings

@contextmanager
def connect():
    dsn = get_settings().database_url
    if not dsn:
        raise HTTPException(503, 'Chưa cấu hình DATABASE_URL cho V2 API/worker.')
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10) as conn:
        yield conn

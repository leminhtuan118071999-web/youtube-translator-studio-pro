"""Integration tests require a disposable LOCAL PostgreSQL database."""
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import pytest
from cryptography.fernet import Fernet
from app.settings import get_settings

@pytest.fixture
def db(monkeypatch):
    dsn = os.getenv('TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set TEST_DATABASE_URL to run PostgreSQL integration tests.')
    if urlsplit(dsn).hostname not in ('127.0.0.1','localhost','postgres'):
        pytest.fail('Integration tests refuse non-local database hosts.')
    monkeypatch.setenv('DATABASE_URL', dsn)
    monkeypatch.setenv('SESSION_ENCRYPTION_KEY', Fernet.generate_key().decode())
    get_settings.cache_clear()
    from app.database import connect
    with connect() as c:
        c.execute('''create schema if not exists auth; create schema if not exists storage;
            do $$ begin create role anon; exception when duplicate_object then null; end $$;
            do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
            create table if not exists auth.users(id uuid primary key);
            create or replace function auth.uid() returns uuid language sql stable as
                $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
            create table if not exists storage.objects(id uuid primary key default gen_random_uuid(),bucket_id text,name text);
            create or replace function storage.foldername(text) returns text[] language sql immutable as
                $$ select string_to_array($1,'/') $$;
            create table if not exists public.youtube_studio_state(user_id uuid primary key,payload jsonb,encrypted_config text,updated_at timestamptz default now());''')
        if not c.execute("select to_regclass('public.lmt_v2_sessions') as t").fetchone()['t']:
            c.execute((Path(__file__).parents[1]/'migrations/001_v2_core.sql').read_text())
            c.execute((Path(__file__).parents[1]/'migrations/002_v2_runtime.sql').read_text())
        owner, other = uuid4(), uuid4()
        c.execute('insert into auth.users(id) values (%s),(%s)', (owner,other))
    yield str(owner), str(other)
    with connect() as c:
        c.execute('delete from auth.users where id=any(%s::uuid[])', ([str(owner),str(other)],))
        c.execute('delete from public.youtube_studio_state where user_id=any(%s::uuid[])', ([str(owner),str(other)],))
    get_settings.cache_clear()

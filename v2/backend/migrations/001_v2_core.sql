-- LMT Studio Pro V2 core schema.
-- Additive only: this migration does not alter or delete any V1 table, row,
-- Auth user, Storage bucket, or Storage object.
-- Apply to the existing Supabase project only after the V2 dry-run report
-- and the migration review are accepted.

create table if not exists public.lmt_v2_legacy_imports (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    source_version integer not null default 1,
    source_updated_at timestamptz,
    source_payload_sha256 text not null,
    raw_payload jsonb not null check (jsonb_typeof(raw_payload) = 'object'),
    encrypted_config text not null default '',
    validation_report jsonb not null default '{}'::jsonb,
    status text not null default 'inspected'
        check (status in ('inspected', 'ready', 'imported', 'failed')),
    created_at timestamptz not null default now(),
    imported_at timestamptz,
    unique (user_id, source_payload_sha256)
);

create table if not exists public.lmt_v2_user_settings (
    user_id uuid primary key references auth.users(id) on delete cascade,
    encrypted_config text not null default '',
    encryption_version text not null default 'fernet-v1',
    settings_version integer not null default 1,
    updated_at timestamptz not null default now()
);

create table if not exists public.lmt_v2_projects (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    name text not null,
    description text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists lmt_v2_projects_owner_updated_idx
    on public.lmt_v2_projects (user_id, updated_at desc);

create table if not exists public.lmt_v2_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    project_id uuid references public.lmt_v2_projects(id) on delete set null,
    legacy_session_id text,
    name text not null default 'Phiên mới',
    status text not null default 'draft'
        check (status in ('draft', 'queued', 'processing', 'completed', 'failed', 'interrupted')),
    data jsonb not null default '{}'::jsonb
        check (jsonb_typeof(data) = 'object'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (legacy_session_id is null or legacy_session_id ~ '^[a-f0-9]{32}$')
);

create unique index if not exists lmt_v2_sessions_legacy_owner_uidx
    on public.lmt_v2_sessions (user_id, legacy_session_id)
    where legacy_session_id is not null;
create index if not exists lmt_v2_sessions_owner_updated_idx
    on public.lmt_v2_sessions (user_id, updated_at desc);

create table if not exists public.lmt_v2_artifacts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    session_id uuid not null references public.lmt_v2_sessions(id) on delete cascade,
    artifact_type text not null,
    content jsonb not null default '{}'::jsonb
        check (jsonb_typeof(content) = 'object'),
    created_at timestamptz not null default now()
);

create index if not exists lmt_v2_artifacts_session_type_idx
    on public.lmt_v2_artifacts (user_id, session_id, artifact_type, created_at desc);

create table if not exists public.lmt_v2_characters (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    session_id uuid not null references public.lmt_v2_sessions(id) on delete cascade,
    character_key text not null,
    profile jsonb not null default '{}'::jsonb
        check (jsonb_typeof(profile) = 'object'),
    image_paths jsonb not null default '[]'::jsonb
        check (jsonb_typeof(image_paths) = 'array'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (user_id, session_id, character_key)
);

create table if not exists public.lmt_v2_jobs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    session_id uuid references public.lmt_v2_sessions(id) on delete set null,
    job_type text not null,
    status text not null default 'queued'
        check (status in ('queued', 'running', 'retry_wait', 'completed', 'failed', 'cancelled')),
    input jsonb not null default '{}'::jsonb
        check (jsonb_typeof(input) = 'object'),
    result jsonb not null default '{}'::jsonb
        check (jsonb_typeof(result) = 'object'),
    encrypted_keys text,
    progress integer not null default 0 check (progress between 0 and 100),
    stage text not null default 'Đang chờ worker',
    attempts integer not null default 0 check (attempts >= 0),
    max_attempts integer not null default 12 check (max_attempts between 1 and 100),
    lease_owner text,
    lease_token uuid,
    lease_expires_at timestamptz,
    retry_after timestamptz not null default now(),
    error text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    finished_at timestamptz
);

create index if not exists lmt_v2_jobs_claim_idx
    on public.lmt_v2_jobs (status, retry_after, lease_expires_at, created_at);
create index if not exists lmt_v2_jobs_owner_session_idx
    on public.lmt_v2_jobs (user_id, session_id, created_at desc);

create table if not exists public.lmt_v2_worker_health (
    name text primary key,
    last_seen timestamptz not null default now(),
    version text not null default '2.0.0'
);

-- RLS and least-privilege grants. Public/anon receives no access.
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'lmt_v2_legacy_imports',
        'lmt_v2_user_settings',
        'lmt_v2_projects',
        'lmt_v2_sessions',
        'lmt_v2_artifacts',
        'lmt_v2_characters',
        'lmt_v2_jobs',
        'lmt_v2_worker_health'
    ] loop
        execute format('alter table public.%I enable row level security', table_name);
        execute format('revoke all on public.%I from public, anon, authenticated', table_name);
    end loop;
end $$;

grant select, insert, update, delete on public.lmt_v2_legacy_imports to authenticated;
grant select, insert, update, delete on public.lmt_v2_user_settings to authenticated;
grant select, insert, update, delete on public.lmt_v2_projects to authenticated;
grant select, insert, update, delete on public.lmt_v2_sessions to authenticated;
grant select, insert, update, delete on public.lmt_v2_artifacts to authenticated;
grant select, insert, update, delete on public.lmt_v2_characters to authenticated;
grant select, insert on public.lmt_v2_jobs to authenticated;
grant select on public.lmt_v2_worker_health to authenticated;

create policy "lmt_v2_imports_select_own" on public.lmt_v2_legacy_imports
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "lmt_v2_imports_insert_own" on public.lmt_v2_legacy_imports
    for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "lmt_v2_imports_update_own" on public.lmt_v2_legacy_imports
    for update to authenticated using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "lmt_v2_settings_select_own" on public.lmt_v2_user_settings
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "lmt_v2_settings_insert_own" on public.lmt_v2_user_settings
    for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "lmt_v2_settings_update_own" on public.lmt_v2_user_settings
    for update to authenticated using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "lmt_v2_projects_select_own" on public.lmt_v2_projects
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "lmt_v2_projects_insert_own" on public.lmt_v2_projects
    for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "lmt_v2_projects_update_own" on public.lmt_v2_projects
    for update to authenticated using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);
create policy "lmt_v2_projects_delete_own" on public.lmt_v2_projects
    for delete to authenticated using ((select auth.uid()) = user_id);

create policy "lmt_v2_sessions_select_own" on public.lmt_v2_sessions
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "lmt_v2_sessions_insert_own" on public.lmt_v2_sessions
    for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "lmt_v2_sessions_update_own" on public.lmt_v2_sessions
    for update to authenticated using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);
create policy "lmt_v2_sessions_delete_own" on public.lmt_v2_sessions
    for delete to authenticated using ((select auth.uid()) = user_id);

create policy "lmt_v2_artifacts_select_own" on public.lmt_v2_artifacts
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "lmt_v2_artifacts_insert_own" on public.lmt_v2_artifacts
    for insert to authenticated with check (
        (select auth.uid()) = user_id
        and exists (
            select 1 from public.lmt_v2_sessions s
            where s.id = session_id and s.user_id = (select auth.uid())
        )
    );
create policy "lmt_v2_artifacts_delete_own" on public.lmt_v2_artifacts
    for delete to authenticated using ((select auth.uid()) = user_id);

create policy "lmt_v2_characters_select_own" on public.lmt_v2_characters
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "lmt_v2_characters_insert_own" on public.lmt_v2_characters
    for insert to authenticated with check (
        (select auth.uid()) = user_id
        and exists (
            select 1 from public.lmt_v2_sessions s
            where s.id = session_id and s.user_id = (select auth.uid())
        )
    );
create policy "lmt_v2_characters_update_own" on public.lmt_v2_characters
    for update to authenticated using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);
create policy "lmt_v2_characters_delete_own" on public.lmt_v2_characters
    for delete to authenticated using ((select auth.uid()) = user_id);

create policy "lmt_v2_jobs_select_own" on public.lmt_v2_jobs
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "lmt_v2_jobs_insert_own" on public.lmt_v2_jobs
    for insert to authenticated with check (
        (select auth.uid()) = user_id
        and status = 'queued'
        and progress = 0
        and attempts = 0
        and result = '{}'::jsonb
        and lease_owner is null
        and lease_token is null
        and lease_expires_at is null
        and finished_at is null
    );

create policy "lmt_v2_worker_health_select_authenticated" on public.lmt_v2_worker_health
    for select to authenticated using (true);

comment on table public.lmt_v2_legacy_imports is
    'Reversible, owner-scoped snapshot of V1 data retained during V2 migration.';
comment on table public.lmt_v2_user_settings is
    'Encrypted provider configuration; encrypted_config uses the existing V1 Fernet key until verified rotation.';
comment on table public.lmt_v2_jobs is
    'Durable V2 job queue; worker mutations occur only through private server-side database credentials.';

-- Durable, owner-scoped work queue for LMT Studio Pro.
-- Requires Supabase Auth. The independent worker uses a private database URL,
-- never the browser-side anon key. SQL is additive and idempotent.
create extension if not exists pgcrypto;

create table if not exists public.lmt_durable_jobs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    session_id text not null check (session_id ~ '^[a-f0-9]{32}$'),
    kind text not null check (kind in ('full', 'video_forms')),
    status text not null default 'queued'
       check (status in ('queued', 'running', 'retry_wait', 'completed', 'failed')),
    snapshot jsonb not null default '{}'::jsonb
       check (jsonb_typeof(snapshot) = 'object'),
    encrypted_keys text,
    result jsonb not null default '{}'::jsonb
       check (jsonb_typeof(result) = 'object'),
    progress integer not null default 0 check (progress between 0 and 100),
    stage text not null default 'Đang chờ worker',
    attempts integer not null default 0 check (attempts between 0 and 100),
    max_attempts integer not null default 18 check (max_attempts between 1 and 100),
    lease_owner text,
    lease_token uuid,
    lease_expires_at timestamptz,
    retry_after timestamptz not null default now(),
    error text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    finished_at timestamptz
);

create index if not exists lmt_jobs_claim_idx
    on public.lmt_durable_jobs (status, retry_after, lease_expires_at, created_at);
create index if not exists lmt_jobs_owner_session_idx
    on public.lmt_durable_jobs (user_id, session_id, created_at desc);
create unique index if not exists lmt_jobs_one_active_kind
    on public.lmt_durable_jobs (user_id, session_id, kind)
    where status in ('queued', 'running', 'retry_wait');

alter table public.lmt_durable_jobs enable row level security;
revoke all on public.lmt_durable_jobs from public, anon, authenticated;
grant select, insert on public.lmt_durable_jobs to authenticated;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'lmt_durable_jobs'
              and policyname = 'LMT jobs: user reads only own'
    ) then
        create policy "LMT jobs: user reads only own"
            on public.lmt_durable_jobs for select to authenticated
            using ((select auth.uid()) = user_id);
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'lmt_durable_jobs'
              and policyname = 'LMT jobs: user submits only new job'
    ) then
        create policy "LMT jobs: user submits only new job"
            on public.lmt_durable_jobs for insert to authenticated
            with check (
                (select auth.uid()) = user_id
                and status = 'queued'
                and progress = 0 and attempts = 0
                and result = '{}'::jsonb
                and lease_token is null and lease_owner is null
                and lease_expires_at is null and finished_at is null
                and encrypted_keys is not null
            );
    end if;
end $$;

-- Private bucket. Workers upload via server-only service key; signed-in users
-- can read images located under their own user UUID prefix.
insert into storage.buckets (id, name, public, file_size_limit)
values ('lmt-character-images', 'lmt-character-images', false, 6291456)
on conflict (id) do nothing;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'storage' and tablename = 'objects'
              and policyname = 'LMT portraits: owner can read'
    ) then
        create policy "LMT portraits: owner can read"
            on storage.objects for select to authenticated
            using (
                bucket_id = 'lmt-character-images'
                and (storage.foldername(name))[1] = (select auth.uid())::text
            );
    end if;
end $$;

comment on table public.lmt_durable_jobs is
 'Durable background tasks with encrypted credentials, owner RLS and retry leases.';

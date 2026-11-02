-- Additive runtime safeguards. Apply after 001, in a single transaction.
begin;
alter table public.lmt_v2_sessions add column if not exists revision bigint not null default 0;
alter table public.lmt_v2_jobs add column if not exists input_revision bigint not null default 0;
alter table public.lmt_v2_jobs add column if not exists request_id uuid;
create unique index if not exists lmt_v2_request_owner_uidx on public.lmt_v2_jobs(user_id,request_id);
create unique index if not exists lmt_v2_one_active_job_uidx on public.lmt_v2_jobs(session_id)
    where status in ('queued','running','retry_wait');
-- Submission/cancellation require validated FastAPI transactions. Direct Data
-- API clients may read owner-scoped jobs but cannot forge results or leases.
revoke insert on public.lmt_v2_jobs from authenticated;
-- Ciphertexts and raw import snapshots stay server-only; encrypted API keys
-- must not appear in public job/status responses.
revoke all on public.lmt_v2_legacy_imports,public.lmt_v2_user_settings from authenticated;
revoke select on public.lmt_v2_jobs from authenticated;
grant select (id,user_id,session_id,job_type,status,progress,stage,attempts,max_attempts,error,
    created_at,updated_at,finished_at,input_revision,request_id) on public.lmt_v2_jobs to authenticated;
commit;

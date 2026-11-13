# LMT Studio Pro V2 — Architecture

## 1. Runtime topology

```text
Browser
  |
  v
Next.js 16 frontend (Dark UI, Supabase SSR Auth)
  |                         |
  | authenticated JWT       | Supabase Auth cookies
  v                         v
FastAPI backend          Existing Supabase Auth
  |
  +--> provider adapters (Gemini / OpenAI / Claude / others)
  |
  +--> durable job submission and status API
  |
  +--> PostgreSQL / Storage using owner-scoped access
             |
             v
       independent Python worker
```

The frontend is presentation and session management only. AI provider secrets and encryption keys stay in backend/worker secret stores. Long-running jobs are executed by an independent worker, not by a browser request or a Next.js request.

## 2. Identity continuity

V2 points to the existing Supabase project. It does not create a new Auth project, recreate users, or change passwords. Supabase Auth remains the identity provider and the existing `auth.users.id` is the stable owner key for V2 rows.

Backend endpoints validate the incoming access token against Supabase Auth before accessing user-owned resources. Database access must be constrained by RLS and `auth.uid()`; never trust a user ID supplied in a request body.

## 3. Legacy data contract

V1 stores one owner row in `public.youtube_studio_state`:
- `user_id`: existing Supabase Auth UUID.
- `payload`: versioned JSON with `workspaces`, `selected_session`, and `saved_session_order`.
- `encrypted_config`: Fernet-encrypted JSON containing provider/API widget settings.
- `updated_at`: last persisted timestamp.

The V1 normalizer accepts up to 150 sessions, preserves known session content fields, and converts an interrupted `running` job into a recoverable interrupted state. V2 must be more lossless than the V1 normalizer: keep unknown legacy fields in a raw JSON column until the import is accepted.

## 4. Additive V2 data model (planned)

All new tables are additive and owner-scoped:
- `lmt_v2_imports`: source version, source timestamp, source checksum, raw payload, encrypted config, import status, validation report.
- `lmt_v2_user_settings`: encrypted provider configuration and settings version.
- `lmt_v2_projects`: user-owned creative projects.
- `lmt_v2_sessions`: one row per imported/created session; unique on (user_id, legacy_session_id) when imported.
- `lmt_v2_artifacts`: translation, SEO, scripts, prompts, generated metadata and file references.
- `lmt_v2_characters`: character profiles and continuity settings.
- `lmt_v2_jobs`: durable queue, leases, retries, checkpoints and job events.

RLS must be enabled on every exposed table. Policies must bind reads/writes to `(select auth.uid()) = user_id`. Updates need both USING and WITH CHECK clauses. Public/anon access is not granted.

No production DDL is included in the scaffold commit. A reviewed migration will be added after the import mapping and policies are tested.

## 5. Encryption and provider keys

V1 uses Fernet to encrypt `encrypted_config`. The exact existing V1 `SESSION_ENCRYPTION_KEY` is required to decrypt it. During migration:
1. Decrypt only inside a private backend process.
2. Validate the decrypted JSON against the allow-list of provider settings.
3. Re-encrypt with the V2 key only if/when a deliberate key rotation is performed.
4. Never log plaintext values, include them in error messages, or send them to the frontend.
5. Keep the V1 key available until the migration is verified and rollback window has closed.

The Supabase publishable key is suitable for browser use. A Supabase secret/service-role key is never exposed in Next.js public environment variables.

## 6. Character images

The current project has a private bucket named `lmt-character-images`. V1 worker paths follow:

```text
<user_uuid>/<session_id>/<safe_character_name>.png
```

V2 keeps this path convention for existing files. Storage remains private; reads use authenticated signed URLs or authenticated Storage downloads. V2 must not copy files unless a dry-run identifies objects requiring path changes.

## 7. Durable jobs

Jobs are persisted before processing. A worker claims a job with a lease, periodically renews it, writes checkpoints, and retries transient failures with bounded backoff. The browser can close without cancelling server-side processing. A job is complete only after its artifacts and status are durably saved.

## 8. Cutover

V1 remains available while V2 is built. Cutover requires:
- same Supabase UID verified after sign-in;
- every V1 session accounted for;
- encrypted provider settings decrypted and validated;
- image references verified;
- translation/SEO/video-form/character regression tests passing;
- worker restart and retry tests passing;
- a tested rollback procedure.

Only then may the production URL be pointed to V2. V1 source, database records and Storage objects remain intact through the rollback window.

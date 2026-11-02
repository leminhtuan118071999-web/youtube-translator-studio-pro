# LMT Studio Pro V2

V2 is a clean rebuild alongside V1. It does not replace or modify the existing Streamlit application until the migration and acceptance gates are complete.

## Decisions

- Dark mode first.
- Reuse the existing Supabase project and Supabase Auth users. Existing user UUIDs must remain unchanged.
- Keep V1 data read-only during the rebuild.
- Migrate legacy sessions and encrypted provider settings only after compatibility checks.
- Never expose service-role/secret keys, database credentials, or the Fernet encryption key to the browser.
- V2 has no public sharing or invite-user feature.

## Repository layout

- `frontend/`: Next.js App Router UI and Supabase SSR authentication.
- `backend/`: FastAPI service for authenticated AI workflows and orchestration.
- `docs/`: architecture and migration notes.

## Local development

### Frontend

1. Copy `.env.example` to `.env.local`.
2. Set the existing Supabase project URL and publishable key.
3. Install dependencies with `npm install`.
4. Run `npm run dev`.

### Backend

1. Create a Python virtual environment.
2. Install `backend/requirements.txt`.
3. Copy `backend/.env.example` to `backend/.env`.
4. Set the same Supabase project URL and publishable key.
5. Start with `uvicorn app.main:app --reload --app-dir backend`.

## Required environment variables

Frontend:
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
- `NEXT_PUBLIC_API_BASE_URL`

Backend:
- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SESSION_ENCRYPTION_KEY` — for the migration phase, this must be the exact Fernet key currently used by V1. Do not generate a replacement until legacy encrypted settings have been migrated and verified.
- `CORS_ORIGINS`

## Migration status

The first V2 commit intentionally contains no production database migration and does not write to the existing Supabase project. Authentication uses the same Supabase Auth service, so an existing user signs in with the same account and receives the same UID.

Before importing legacy data, the migration tool must:
1. Read the signed-in user's V1 `youtube_studio_state` row under that user's JWT/RLS.
2. Validate the JSON payload version and session shape.
3. Decrypt `encrypted_config` only in the backend using the exact V1 Fernet key.
4. Validate each provider setting without logging or returning secret values.
5. Preserve the raw legacy payload and encrypted blob in a reversible import record.
6. Import sessions idempotently, keyed by `user_id` and legacy session ID.
7. Verify session counts, content hashes, provider-setting counts, and image object references.
8. Mark the import complete only after all checks pass.

The existing private `lmt-character-images` bucket is retained. V2 must preserve its `user_id/session_id/file.png` object path convention and must never make the bucket public.

## Current status

- [x] V2 branch created.
- [x] Initial frontend/backend scaffold.
- [x] Existing Supabase project and legacy schema audited read-only.
- [ ] Legacy import adapter and dry-run report.
- [ ] Translation, SEO, video-form and character workflows.
- [ ] Durable queue and independent worker.
- [ ] End-to-end tests and deployment.
- [ ] Production cutover after acceptance.

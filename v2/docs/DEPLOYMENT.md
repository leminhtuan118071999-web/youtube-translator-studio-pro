# Deploy and replace V1

## Services

Deploy the committed `v2/render.yaml` Blueprint from the existing repository.
Select the intended branch/commit and set the Blueprint path to `v2/render.yaml`.
All three services are defined as always-on paid `0.5c-512mb` instances. Review the
current Render quotation before applying; the repository does not provision or
charge resources by itself. Reuse the existing Supabase project/database.

The API/worker build from the repository root. Do not set their root directory
to `v2/backend` or the shared V1 engines will be missing. The frontend uses
`v2/frontend` as its root.

## Environment

Frontend (public, baked into build):

- `NEXT_PUBLIC_SUPABASE_URL`: existing Supabase URL.
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: existing publishable/anon key.
- `NEXT_PUBLIC_API_BASE_URL`: the new HTTPS API URL, without trailing slash.

API (private server environment):

- `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` for authentication and owner-signed Storage reads.
- `DATABASE_URL`: private Supabase PostgreSQL/pooler DSN with SSL.
- `SESSION_ENCRYPTION_KEY`: exact Fernet key from V1; never generate a substitute.
- `CORS_ORIGINS`: comma-separated exact frontend HTTPS origins.
- `SUPABASE_SERVICE_ROLE_KEY`: required for reference-image capability checks.

Worker (private server environment):

- Same `DATABASE_URL` and `SESSION_ENCRYPTION_KEY`.
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` to persist images. No browser token
  or refresh token is stored in a job; it continues after the user's login expires.

Keep DSNs, service-role keys and Fernet keys out of all frontend env vars, logs
and source control. Provider credentials are configured by the user after sign-in
or imported from V1, encrypted at rest and copied encrypted into each job.

Add the actual frontend URL and `/auth/callback` to Supabase Auth redirect URLs.
Password recovery uses `/auth/callback?next=/reset-password`. The callback permits
only the dashboard or reset route as its destination. Do not change existing V1
redirect URLs while V1 is needed.

## Database

Run the V1 compatibility dry-run with the correct Fernet key. Review and apply
`001_v2_core.sql`, then `002_v2_runtime.sql`. These are additive SQL files; do not
run them repeatedly or edit/remove V1 migrations. RLS remains enabled and no
Storage bucket becomes public. Keep the existing private `lmt-character-images`
bucket and its owner prefix.

`DATABASE_URL` is a privileged **server-only** connection for atomic transactions.
FastAPI validates the bearer token with Supabase before it issues owner-bound
queries. Worker methods use job IDs plus owner IDs, revision checks, lease tokens
and lease expiry. Direct browser access is constrained separately by RLS; encrypted
settings, raw import snapshots and job ciphertexts are not public-readable.

## Acceptance before switching the public URL

1. API `/health` is live; sign-in uses the same V1 user UUID.
2. Dry-run succeeds; import session counts/checksums reconcile. Re-run the import
   and confirm no duplicate sessions or changed V2 edits/settings.
3. Verify every required image reference. Export any V1 in-memory images before
   stopping Streamlit. Database import does not import ZIPs downloaded locally.
4. Use a short real story to check translation, number spelling, SEO, profiles,
   wardrobe continuity, paired prompts, subtitles and image download.
5. Close the browser while a job runs. Confirm checkpoint and completion after
   reopening. Restart the worker mid-job and verify lease recovery.
6. Edit/delete/cancel a running session and confirm no old result returns.
7. Point the intended public URL at the V2 frontend only after these pass. Record
   the live Render deploy IDs and exact commit. Streamlit cannot serve Next.js.

No production deployment or cutover is implied by a passing local build or GitHub
merge. Rollback: route traffic back to V1; keep V2 tables and snapshots for audit.
V1 data/Auth/Storage objects remain intact. Do not remove V1 until its rollback
window and in-memory image preservation have been completed.

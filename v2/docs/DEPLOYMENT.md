# V2 deployment guide

V2 is deployed independently from V1. Do not change the V1 Streamlit URL during this stage.

## 1. Deploy the FastAPI backend on Render

1. Open the Render dashboard and create a new Blueprint/Web Service from the GitHub repository.
2. Select branch `v2/rebuild-foundation` and configuration file `v2/render.yaml`.
3. Set the environment variables in Render:
   - `SUPABASE_URL`: the existing Supabase project URL.
   - `SUPABASE_PUBLISHABLE_KEY`: the existing project's publishable key.
   - `SESSION_ENCRYPTION_KEY`: the exact Fernet key currently configured in V1 Streamlit Secrets. Copy it directly from the private secret store; do not paste it into chat or GitHub.
   - `CORS_ORIGINS`: the V2 Vercel domain, without a trailing slash.
4. Deploy and check `https://<render-service-domain>/health`.

The Render service in the initial blueprint uses the free web-service plan and may sleep when idle. It is sufficient for the initial authentication and migration dry-run API. Durable AI jobs will use a separate worker service in a later phase.

## 2. Deploy the frontend on Vercel

1. Import the same GitHub repository into Vercel.
2. Select branch `v2/rebuild-foundation`.
3. Set Root Directory to `v2/frontend`.
4. Add environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL`: the existing Supabase project URL.
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: the existing publishable key.
   - `NEXT_PUBLIC_API_BASE_URL`: the Render API base URL, without a trailing slash.
5. Deploy the preview URL. Do not assign the V1 production domain yet.

## 3. Verify identity and V1 compatibility

1. Open the V2 preview URL.
2. Sign in using the existing Supabase account. Do not create a duplicate user.
3. Confirm the dashboard displays the same account and UID as V1.
4. Click **Chạy kiểm tra tương thích**.
5. Confirm the report finds the legacy row, validates all sessions, and decrypts the legacy provider configuration successfully.

If the report says `legacy_encryption_key_missing` or `legacy_encryption_verification_failed`, stop. Re-check the private Render `SESSION_ENCRYPTION_KEY` value against the V1 Streamlit secret. Never rotate or regenerate it during migration.

## 4. Production cutover

Production cutover is a separate, later approval. It requires a successful data import, image checks, feature regression tests, worker restart tests and a verified rollback procedure. Until then, V1 remains the production app.

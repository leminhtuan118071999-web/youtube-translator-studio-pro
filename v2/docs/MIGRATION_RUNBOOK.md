# V1 → V2 migration runbook

## Safety rules

- Do not modify or delete V1 tables during the V2 rebuild.
- Do not create a new Supabase Auth project. Keep the current project so user UUIDs and passwords remain valid.
- Do not run `001_v2_core.sql` against production until the dry-run report and SQL review are accepted.
- Keep the V1 Fernet key available in the private backend environment until every encrypted provider setting is verified.
- Never paste the Fernet key, API keys, service-role key, database password, or recovery tokens into chat or GitHub.

## Read-only dry run

After the backend is configured, sign in to V2 with the existing account and call:

```http
GET /v1/migration/legacy/dry-run
Authorization: Bearer <current Supabase access token>
```

The endpoint reads only the caller's `youtube_studio_state` row through Supabase REST using the caller JWT and existing RLS. It returns counts, validation flags and SHA-256 checksums only. It does not write data and does not return session text or decrypted provider values.

The report must show:
- `legacy_state_found = true`
- `ready_for_import = true`
- `encryption_verified = true` when an encrypted config exists
- session count matches the V1 row
- no invalid session IDs or invalid records

If the encryption key is missing or wrong, the report blocks import. Do not replace the old key to bypass the check.

## Image handling

The existing bucket `lmt-character-images` is private. V1 worker paths use `<user_uuid>/<session_id>/<file>.png`. Keep the bucket private and retain all object paths.

Important V1 behavior: `CharacterImageStore` in `character_images.py` is process-memory storage. Images that were not uploaded to Supabase Storage are not part of the database backup and can disappear when the V1 server process restarts. V1 can export a ZIP of a session's images while those images are still available. Download any needed per-session image ZIPs from V1 before retiring or restarting its process; V2 will provide a controlled import path that keeps the original user/session folder convention.

The initial read-only audit found:
- 0 objects in the existing private Storage bucket;
- 0 non-empty character-image manifests across the 4 V1 sessions inspected.

Therefore, no character images are currently persisted in the Supabase bucket. This does not prove that V1's in-memory image cache or files already downloaded to the user's computer are empty. Do not shut down V1 until any still-needed in-memory images have been exported.

## Import procedure (later phase)

1. Create a reversible V1 snapshot row in `lmt_v2_legacy_imports`.
2. Copy the encrypted config blob unchanged into `lmt_v2_user_settings`; do not decrypt/re-encrypt unless a deliberate rotation is approved.
3. Upsert each session by (user_id, legacy_session_id), preserving the entire raw session JSON in `data`.
4. Copy artifact and character metadata only after the session row has been verified.
5. Preserve existing Storage object paths. Import V1 ZIP archives only when necessary, validating every PNG and mapping it to the correct legacy session ID.
6. Verify source/target session counts, per-session hashes, provider setting counts and image references.
7. Mark the import complete only after all checks pass.

## Rollback

V1 remains untouched. If V2 import or validation fails, stop V2 writes and continue using V1. The snapshot table and V1 source row remain available for retry. Do not delete V1 data as part of rollback.

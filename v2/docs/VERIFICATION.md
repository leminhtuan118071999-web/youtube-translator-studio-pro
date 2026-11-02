# V2 verification

Verified locally during this implementation:

- Production Next.js build and TypeScript check.
- Backend syntax compilation.
- PostgreSQL integration coverage for lossless/idempotent V1 import, rollback on
  wrong encryption, owner isolation/RLS, hidden credential ciphertexts, concurrent
  edits, request idempotency, one active job per session, cancel/delete fencing,
  expiry/reclaim of a lease, final-attempt cleanup, checkpoint resume and atomic
  exactly-once result application.
- One real V1 narration/SEO engine flow through the V2 worker using a mocked
  provider boundary and durable PostgreSQL result storage.
- 61 regression tests for shared narration, number spelling, metadata, V1 storage,
  V1 queue, profiles, identity, wardrobe and speech roles.
- Next.js updated from 16.4.0 to 16.4.3 after the production build flagged the
  existing vulnerable framework version. Official advisory:
  https://nextjs.org/blog/nextjs-security-update-october-14-2026

Local database tests use a disposable PGlite PostgreSQL protocol server. CI uses
an actual PostgreSQL 17 service, with fake Auth/Storage schemas to test RLS and
transactions. Neither test environment touches the production Supabase project.

Not yet established by local tests: real AI-provider quality/quota/access,
production Supabase credentials, Storage delivery, browser end-to-end flow,
live Render deployments or actual production cutover. These must be recorded
as deployment acceptance evidence, not inferred from a build.

The legacy full V1 suite was already failing at the starting commit. Its source
is unchanged. V1 CI is now scoped to V1 runtime changes, while V2 CI runs the V2
integration suite plus the shared-engine regression group. This avoids treating
unmodified legacy UI expectations as V2 deployment evidence.

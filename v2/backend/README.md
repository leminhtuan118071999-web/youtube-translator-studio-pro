# LMT V2 API and independent worker

From the repository root:

```bash
pip install -r v2/backend/requirements.txt
uvicorn app.main:app --app-dir v2/backend --reload
```

Set backend environment variables using `v2/backend/.env.example`. Environment
files are resolved from the process working directory. Production should use
host-managed secrets, not committed files.

Run the independent worker from `v2/backend` with `python -m app.worker`.
It imports the existing root engines, so deploy the **whole repository**; do not
package only the backend subdirectory. Streamlit is retained as a dependency
because the existing video planner imports its UI helper module. V2 never calls
Streamlit to render pages or store state.

The server-only `DATABASE_URL` permits atomic owner-scoped transactions across
sessions, jobs and checkpoints. Supabase validates every API bearer token.
Never expose this privileged connection string or the encryption key in a
`NEXT_PUBLIC_` variable. Every user-data query explicitly binds the authenticated
owner. RLS also protects direct Data API access. Jobs/settings/import snapshots
cannot be written/read as ciphertext through the public client.

Use `/docs` for the complete API contract. Routes include:

- `/v1/sessions`: list, create, edit with revision checking, delete and cancel jobs.
- `/v1/settings`, `/v1/providers`: encrypted provider settings and connection/model checks.
- `/v1/sessions/{id}/jobs`: translation/SEO, standalone SEO, profiles, forms and images.
- `/v1/jobs`: progress, cancellation, resume failed jobs with unchanged input.
- `/v1/migration/legacy/dry-run`, `/v1/migration/legacy/import`: inspected, transactional import.
- `/v1/sessions/{id}/export`, `/thumbnail`, `/images`, `/images.zip`: exports and private images.

## Tests

`pytest -q` runs non-database tests. Set `TEST_DATABASE_URL` to a disposable local
PostgreSQL database to also run transaction, RLS, ownership, fencing and recovery
integration tests. Tests refuse remote database hosts. CI provisions PostgreSQL
17 and runs these tests; it never connects to production.

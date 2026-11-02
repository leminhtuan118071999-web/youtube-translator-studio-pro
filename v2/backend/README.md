# V2 API

FastAPI backend for authenticated LMT Studio Pro V2 workflows.

Run from this directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The initial API exposes:
- `GET /health`: liveness check.
- `GET /v1/auth/me`: validates the Supabase bearer token and returns the authenticated user's ID/email only.

AI workflow routes, legacy migration endpoints and durable jobs will be added after the data model and security policies are reviewed.

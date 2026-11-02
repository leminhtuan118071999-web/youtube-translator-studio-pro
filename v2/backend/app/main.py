import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .auth import AuthenticatedUser, require_user
from .legacy_migration import inspect_legacy_state
from .settings import get_settings

settings = get_settings()

app = FastAPI(
    title="LMT Studio Pro V2 API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lmt-studio-pro-v2-api", "version": "2.0.0"}


@app.get("/v1/auth/me")
async def current_user(user: AuthenticatedUser = Depends(require_user)):
    return {"id": user.id, "email": user.email}


@app.get("/v1/migration/legacy/dry-run")
async def legacy_migration_dry_run(user: AuthenticatedUser = Depends(require_user)):
    """Inspect the caller's V1 row using their JWT and existing RLS policies.

    This endpoint is read-only. It returns validation counts only and does not
    import, mutate, or delete any V1/V2 data.
    """
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(status_code=503, detail="Supabase backend configuration is missing.")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                settings.supabase_url.rstrip("/") + "/rest/v1/youtube_studio_state",
                headers={
                    "apikey": settings.supabase_publishable_key,
                    "Authorization": f"Bearer {user.access_token}",
                },
                params={
                    "select": "payload,encrypted_config,updated_at",
                    "user_id": f"eq.{user.id}",
                    "limit": "1",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Legacy data store is unavailable.") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Could not inspect the legacy data row.")

    rows = response.json()
    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="Legacy data response has an invalid shape.")

    if not rows:
        return {
            "legacy_state_found": False,
            "ready_for_import": True,
            "session_count": 0,
            "provider_setting_count": 0,
            "encryption_verified": True,
            "message": "No V1 state row exists for this signed-in user.",
        }

    row = rows[0]
    report = inspect_legacy_state(
        row.get("payload"),
        row.get("encrypted_config"),
        settings.session_encryption_key,
    )
    return {
        "legacy_state_found": True,
        "legacy_updated_at": row.get("updated_at"),
        **report,
    }

# Runtime endpoints are synchronous where they use PostgreSQL/legacy engines;
# FastAPI runs them in its threadpool, keeping the event loop available.
from .routes import router
from fastapi.responses import JSONResponse
from psycopg import Error as DatabaseError
app.include_router(router)

@app.exception_handler(DatabaseError)
async def database_error(request, exc):
    # Never return connection strings, SQL, encrypted keys or provider content.
    return JSONResponse(status_code=503, content={'detail': 'Kho dữ liệu V2 chưa sẵn sàng. Kiểm tra kết nối và migration trên máy chủ.'})

from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(status_code=422, content={'detail': 'Dữ liệu yêu cầu không hợp lệ. Kiểm tra kiểu và giới hạn các trường.'})

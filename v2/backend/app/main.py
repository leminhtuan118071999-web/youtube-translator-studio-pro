from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import AuthenticatedUser, require_user
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

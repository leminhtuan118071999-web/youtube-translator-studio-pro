from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .auth import AuthenticatedUser, require_user
from .settings import get_settings

settings = get_settings()

app = FastAPI(
    title="LMT Studio Pro V2 API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(GZipMiddleware, minimum_size=1500, compresslevel=3)
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


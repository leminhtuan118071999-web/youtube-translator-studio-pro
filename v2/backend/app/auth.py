from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .settings import get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required.")

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(status_code=503, detail="Supabase backend configuration is missing.")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                settings.supabase_url.rstrip("/") + "/auth/v1/user",
                headers={
                    "apikey": settings.supabase_publishable_key,
                    "Authorization": f"Bearer {credentials.credentials}",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Authentication service is unavailable.") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    payload = response.json()
    user_id = payload.get("id")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Invalid authenticated identity.")

    return AuthenticatedUser(id=user_id, email=payload.get("email"))

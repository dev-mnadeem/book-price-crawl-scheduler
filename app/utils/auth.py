from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

from app.config.settings import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def api_key_auth(x_api_key: str | None = Security(api_key_header)) -> str:
    if not x_api_key or x_api_key not in settings.api_keys_list:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
    return x_api_key

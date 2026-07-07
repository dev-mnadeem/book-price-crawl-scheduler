from __future__ import annotations

from typing import Set

from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

from app.config.settings import settings


def _api_key_set() -> Set[str]:
    keys = set(settings.api_keys_list)
    return keys


# Document the header in OpenAPI via APIKeyHeader security scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def api_key_auth(x_api_key: str | None = Security(api_key_header)) -> str:
    if not x_api_key or x_api_key not in _api_key_set():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
    return x_api_key

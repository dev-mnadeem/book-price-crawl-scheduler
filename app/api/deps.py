from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.db.mongo import get_db
from app.utils.auth import api_key_auth
from app.utils.rate_limiter import rate_limit


APIKeyDep = Annotated[str, Depends(api_key_auth)]


async def rate_limit_dep(api_key: APIKeyDep) -> None:
    await rate_limit(api_key)


DBDep = Depends(get_db)

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import DBDep, rate_limit_dep
from app.utils.auth import api_key_auth
from app.models.change import ChangesResponse

router = APIRouter(
    prefix="/changes",
    tags=["changes"],
    dependencies=[Depends(api_key_auth), Depends(rate_limit_dep)],
)


@router.get(
    "",
    response_model=ChangesResponse,
    summary="List recent changes",
    description="View recent updates (e.g., new books added, updates detected) ordered by most recent first.",
)
async def list_changes(
    db: AsyncIOMotorDatabase = DBDep,
    since: Optional[str] = Query(default=None, description="Only return changes at or after this timestamp (ISO 8601)."),
    type: Optional[Literal["new", "update"]] = Query(default=None, alias="type", description="Filter by change type."),
    limit: int = Query(default=100, ge=1, le=500, description="Max number of items to return."),
    offset: int = Query(default=0, ge=0, description="Number of items to skip (for pagination)."),
):
    q: dict = {}
    if since is not None:
        s = since.strip().replace(" ", "+")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            q["timestamp"] = {"$gte": dt}
        except ValueError:
            pass
    if type is not None:
        q["change_type"] = type

    cursor = (
        db["changes"].find(q, projection={"_id": 0})
        .sort("timestamp", -1)
        .skip(offset)
        .limit(limit)
    )
    items = [doc async for doc in cursor]
    return {"items": items, "count": len(items)}

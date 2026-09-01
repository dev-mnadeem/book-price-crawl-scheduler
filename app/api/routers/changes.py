from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import DBDep, rate_limit_dep
from app.utils.auth import api_key_auth
from app.analysis.significance import SEVERITY_ORDER
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
    severity: Optional[Literal["critical", "notable", "minor", "cosmetic"]] = Query(
        default=None,
        description="Only return changes of this severity. Use 'critical' for the ones that need attention today.",
    ),
    min_severity: Optional[Literal["critical", "notable", "minor", "cosmetic"]] = Query(
        default=None,
        description="Return this severity and anything more urgent.",
    ),
    order: Literal["recent", "severity"] = Query(
        default="recent",
        description="'severity' ranks the most urgent first, then most recent.",
    ),
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
    if severity is not None:
        q["severity"] = severity
    elif min_severity is not None:
        # "at least this urgent" — the bands more severe than the one asked for.
        wanted = [s for s, rank in SEVERITY_ORDER.items() if rank <= SEVERITY_ORDER[min_severity]]
        q["severity"] = {"$in": wanted}

    if order == "severity":
        # Severity is a word, and Mongo would sort it alphabetically —
        # "cosmetic" before "critical", which is exactly backwards. Project a
        # numeric rank and sort on that.
        cursor = db["changes"].aggregate([
            {"$match": q},
            {"$addFields": {"severity_rank": {"$switch": {
                "branches": [
                    {"case": {"$eq": ["$severity", name]}, "then": rank}
                    for name, rank in SEVERITY_ORDER.items()
                ],
                "default": 9,
            }}}},
            {"$sort": {"severity_rank": 1, "timestamp": -1}},
            {"$skip": offset},
            {"$limit": limit},
            {"$project": {"_id": 0, "severity_rank": 0}},
        ])
    else:
        cursor = (
            db["changes"].find(q, projection={"_id": 0})
            .sort("timestamp", -1)
            .skip(offset)
            .limit(limit)
        )
    items = [doc async for doc in cursor]
    return {"items": items, "count": len(items)}

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import orjson
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.settings import settings
from app.utils.time import now_utc


async def generate_daily_report(db: AsyncIOMotorDatabase, since: Optional[datetime] = None) -> Path:
    ts = now_utc()
    start_of_day = datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)
    since = since or start_of_day

    q = {"timestamp": {"$gte": since}}
    cursor = db["changes"].find(q, projection={"_id": 0}).sort("timestamp", -1)
    items = [doc async for doc in cursor]

    out_dir = Path(settings.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outfile = out_dir / f"{ts.date().isoformat()}.json"

    payload = {"generated_at": ts.isoformat(), "since": since.isoformat(), "count": len(items), "items": items}
    outfile.write_bytes(orjson.dumps(payload))
    return outfile

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


async def acquire_lock(
    db: AsyncIOMotorDatabase,
    name: str,
    owner: Optional[str] = None,
    ttl_seconds: int = 6 * 3600,
) -> bool:
    """Try to acquire a named lock document. Returns True if acquired.

    Uses an atomic findOneAndUpdate pattern with an expiry window.
    """
    now = datetime.utcnow()
    owner = owner or f"pid:{os.getpid()}"
    expires_at = now + timedelta(seconds=ttl_seconds)

    # Filters and update doc
    lock_filter_available = {"_id": name, "$or": [{"locked": False}, {"expires_at": {"$lt": now}}]}
    update_doc = {
        "$set": {
            "_id": name,
            "locked": True,
            "owner": owner,
            "acquired_at": now,
            "expires_at": expires_at,
        }
    }

    locks = db["locks"]

    # acquire by updating an existing unlocked/expired lock (atomic)
    res = await locks.find_one_and_update(
        lock_filter_available,
        update_doc,
        upsert=False,
        return_document=ReturnDocument.AFTER,
    )
    if res:
        return True

    # If no existing, try to insert a new one
    try:
        await locks.insert_one(
            {
                "_id": name,
                "locked": True,
                "owner": owner,
                "acquired_at": now,
                "expires_at": expires_at,
            }
        )
        return True
    except DuplicateKeyError:
        # Someone else inserted concurrently
        return False


async def release_lock(db: AsyncIOMotorDatabase, name: str, owner: Optional[str] = None) -> None:
    owner = owner or f"pid:{os.getpid()}"
    await db["locks"].update_one(
        {"_id": name, "owner": owner},
        {"$set": {"locked": False}, "$unset": {"owner": "", "acquired_at": "", "expires_at": ""}},
    )

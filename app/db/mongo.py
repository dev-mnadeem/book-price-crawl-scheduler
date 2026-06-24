from __future__ import annotations

import logging
from typing import Optional

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config.settings import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncMongoClient] = None


async def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        logger.info("Creating MongoDB client", extra={"database": settings.mongodb_db})
        # tz_aware so timestamps come back as UTC rather than naive datetimes.
        _client = AsyncMongoClient(settings.mongodb_uri, tz_aware=True)
    return _client


async def get_db() -> AsyncDatabase:
    client = await get_client()
    return client[settings.mongodb_db]


async def close_client() -> None:
    global _client
    if _client is not None:
        logger.info("Closing MongoDB client")
        await _client.close()
        _client = None

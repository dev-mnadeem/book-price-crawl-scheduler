from __future__ import annotations

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config.settings import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None


async def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        logger.info("Creating MongoDB client", extra={"uri": settings.mongodb_uri})
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


async def get_db() -> AsyncIOMotorDatabase:
    client = await get_client()
    return client[settings.mongodb_db]


async def close_client() -> None:
    global _client
    if _client is not None:
        logger.info("Closing MongoDB client")
        _client.close()
        _client = None

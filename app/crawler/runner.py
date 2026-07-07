from __future__ import annotations

import asyncio
import logging

from app.config.logging import setup_logging
from app.config.settings import settings
from app.db.indexes import ensure_indexes
from app.db.mongo import close_client, get_db
from app.crawler.crawler import run_full_crawl
from app.db.locks import acquire_lock, release_lock

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging(settings.log_level)
    db = await get_db()
    await ensure_indexes(db)
    lock_name = "crawl_lock"
    got = await acquire_lock(db, lock_name, owner="runner")
    if not got:
        logger.info("Another crawl is in progress; exiting runner")
        print({"status": "skipped", "reason": "lock_not_acquired"})
        await close_client()
        return
    try:
        summary = await run_full_crawl(db)
        logger.info("One-off crawl finished", extra=summary)
        print(summary)
    finally:
        await release_lock(db, lock_name, owner="runner")
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())

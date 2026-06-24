from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config.logging import setup_logging
from app.config.settings import settings
from app.crawler.crawler import run_full_crawl
from app.db.indexes import ensure_indexes
from app.db.locks import acquire_lock, release_lock
from app.db.mongo import close_client, get_db
from app.scheduler.report import generate_daily_report

logger = logging.getLogger(__name__)


LOCK_NAME = "crawl_lock"


async def job(owner: str = "scheduler") -> None:
    db = await get_db()
    await ensure_indexes(db)
    # The startup run goes through the lock too: a crawl started by another
    # process (the compose crawl job, a second API replica) is not stale just
    # because this process has only now booted. Locks left by a crashed
    # process expire on their own.
    if not await acquire_lock(db, LOCK_NAME, owner=owner):
        logger.info("Another crawl is in progress; skipping this run", extra={"owner": owner})
        return
    try:
        summary = await run_full_crawl(db)
        logger.info("Scheduled crawl finished", extra=summary)
        await generate_daily_report(db)
    finally:
        await release_lock(db, LOCK_NAME, owner=owner)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    if settings.scheduler_interval_seconds and settings.scheduler_interval_seconds > 0:
        trigger = IntervalTrigger(seconds=settings.scheduler_interval_seconds)
        logger.info("Using interval trigger", extra={"seconds": settings.scheduler_interval_seconds})
    else:
        trigger = CronTrigger.from_crontab(settings.scheduler_cron)
        logger.info("Using cron trigger", extra={"cron": settings.scheduler_cron})

    scheduler.add_job(job, trigger, id="crawl_job", name="crawl_job", replace_existing=True)
    if settings.scheduler_run_on_start:
        scheduler.add_job(
            job,
            "date",
            run_date=datetime.now(timezone.utc),
            id="initial_crawl",
            name="initial_crawl",
            replace_existing=True,
            kwargs={"owner": "initial"},
        )
    return scheduler


async def main() -> None:
    setup_logging(settings.log_level)
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("Scheduler started")
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
        await close_client()


_embedded_scheduler: AsyncIOScheduler | None = None


async def start_scheduler_embedded() -> None:
    global _embedded_scheduler
    if _embedded_scheduler is not None:
        return
    _embedded_scheduler = build_scheduler()
    _embedded_scheduler.start()
    logger.info("Embedded scheduler started")


async def stop_scheduler_embedded() -> None:
    global _embedded_scheduler
    if _embedded_scheduler is not None:
        _embedded_scheduler.shutdown(wait=False)
        _embedded_scheduler = None
        logger.info("Embedded scheduler stopped")


if __name__ == "__main__":
    asyncio.run(main())

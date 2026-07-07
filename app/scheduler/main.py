from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone, timedelta

from app.config.logging import setup_logging
from app.config.settings import settings
from app.crawler.crawler import run_full_crawl
from app.db.indexes import ensure_indexes
from app.db.mongo import close_client, get_db
from app.scheduler.report import generate_daily_report
from app.db.locks import acquire_lock, release_lock

logger = logging.getLogger(__name__)


LOCK_NAME = "crawl_lock"


async def job(skip_lock: bool = False, owner: str = "scheduler") -> None:
    db = await get_db()
    await ensure_indexes(db)
    acquired = False
    if skip_lock:
        # Force-take the lock for the initial seeding run to avoid skipping due to stale locks
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=6)
        await (await get_db())["locks"].update_one(
            {"_id": LOCK_NAME},
            {"$set": {"locked": True, "owner": owner, "acquired_at": now, "expires_at": expires_at}},
            upsert=True,
        )
        acquired = True
    else:
        got = await acquire_lock(db, LOCK_NAME, owner=owner)
        if not got:
            logger.info("Another crawl is in progress; skipping scheduled run")
            return
        acquired = True
    try:
        summary = await run_full_crawl(db)
        logger.info("Scheduled crawl finished", extra=summary)
        await generate_daily_report(db)
    finally:
        if acquired:
            await release_lock(db, LOCK_NAME, owner=owner)


async def main() -> None:
    setup_logging(settings.log_level)
    scheduler = AsyncIOScheduler()
    if settings.scheduler_interval_seconds and settings.scheduler_interval_seconds > 0:
        trigger = IntervalTrigger(seconds=settings.scheduler_interval_seconds)
        logger.info("Using interval trigger", extra={"seconds": settings.scheduler_interval_seconds})
    else:
        trigger = CronTrigger.from_crontab(settings.scheduler_cron)
        logger.info("Using cron trigger", extra={"cron": settings.scheduler_cron})

    scheduler.add_job(job, trigger, id="crawl_job", name="crawl_job", replace_existing=True)
    if settings.scheduler_run_on_start:
        # Schedule an immediate one-off run on startup without blocking due to stale locks
        scheduler.add_job(
            job,
            'date',
            run_date=datetime.now(timezone.utc),
            id="initial_crawl",
            name="initial_crawl",
            replace_existing=True,
            kwargs={"skip_lock": True, "owner": "initial"},
        )

    scheduler.start()
    logger.info("Scheduler started")
    try:
        await asyncio.Event().wait()
    finally:
        await close_client()


_embedded_scheduler: AsyncIOScheduler | None = None


async def start_scheduler_embedded() -> None:
    global _embedded_scheduler
    if _embedded_scheduler is not None:
        return
    sched = AsyncIOScheduler()
    if settings.scheduler_interval_seconds and settings.scheduler_interval_seconds > 0:
        trigger = IntervalTrigger(seconds=settings.scheduler_interval_seconds)
    else:
        trigger = CronTrigger.from_crontab(settings.scheduler_cron)
    sched.add_job(job, trigger, id="crawl_job", name="crawl_job", replace_existing=True)
    if settings.scheduler_run_on_start:
        sched.add_job(
            job,
            'date',
            run_date=datetime.now(timezone.utc),
            id="initial_crawl",
            name="initial_crawl",
            replace_existing=True,
            kwargs={"skip_lock": True, "owner": "initial"},
        )
    sched.start()
    _embedded_scheduler = sched
    logger.info("Embedded scheduler started")


async def stop_scheduler_embedded() -> None:
    global _embedded_scheduler
    if _embedded_scheduler is not None:
        _embedded_scheduler.shutdown(wait=False)
        _embedded_scheduler = None
        logger.info("Embedded scheduler stopped")


if __name__ == "__main__":
    asyncio.run(main())

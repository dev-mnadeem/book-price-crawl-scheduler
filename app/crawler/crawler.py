from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Tuple

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.analysis.significance import classify
from app.config.settings import settings
from app.models.change import ChangeLog, FieldDiff
from app.utils.hashing import content_hash
from app.utils.http_client import fetch_text, get_http_client
from app.utils.text import normalize_category
from app.utils.time import now_utc

from .parser import parse_book_detail, parse_category_links, parse_listing_page

logger = logging.getLogger(__name__)

DIFF_FIELDS = (
    "name",
    "description",
    "category",
    "price_excl_tax",
    "price_incl_tax",
    "availability",
    "num_reviews",
    "image_url",
    "rating",
    "in_stock",
)


async def _gather_all_detail_urls(category_url: str, client: httpx.AsyncClient) -> List[str]:
    page_url = category_url
    detail_urls: List[str] = []
    seen_pages: set[str] = set()
    while page_url and page_url not in seen_pages:
        seen_pages.add(page_url)
        html = await fetch_text(page_url, client=client)
        details, page_url = parse_listing_page(html, page_url)
        detail_urls.extend(details)
    return list(dict.fromkeys(detail_urls))


def _diff(old: dict, new: dict) -> List[FieldDiff]:
    return [
        FieldDiff(field=f, old=old.get(f), new=new.get(f))
        for f in DIFF_FIELDS
        if (old.get(f) or None) != (new.get(f) or None)
    ]


def _change(upc: str, change_type: str, diffs: List[FieldDiff], now) -> dict:
    return ChangeLog(
        book_upc=upc,
        change_type=change_type,
        changes=diffs,
        timestamp=now,
        **classify(diffs, change_type).as_dict(),
    ).model_dump()


async def _process_book(
    url: str, db: AsyncIOMotorDatabase, sem: asyncio.Semaphore, client: httpx.AsyncClient
) -> Tuple[str, str]:
    async with sem:
        html = await fetch_text(url, client=client)
    parsed = parse_book_detail(html, page_url=url, base_url=settings.base_url)
    if not parsed.get("upc"):
        logger.warning("Missing UPC, skipping", extra={"url": url})
        return url, "missing_upc"

    parsed["in_stock"] = (parsed.get("availability") or 0) > 0
    parsed["currency"] = "GBP"
    parsed["category_norm"] = normalize_category(parsed.get("category"))

    new_hash = content_hash(parsed)
    now = now_utc()
    seen = {"last_seen": now, "crawl_timestamp": now}

    existing = await db["books"].find_one({"upc": parsed["upc"]})
    if not existing:
        await db["books"].insert_one(
            {**parsed, **seen, "content_hash": new_hash, "raw_html": html, "first_seen": now, "last_status": "inserted"}
        )
        await db["changes"].insert_one(_change(parsed["upc"], "new", [], now))
        return url, "inserted"

    # Rehashing the stored fields rather than trusting the stored hash keeps
    # documents written under an older hashing scheme from all reading as
    # changed after an upgrade.
    if content_hash(existing) == new_hash:
        await db["books"].update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    **seen,
                    "last_status": "unchanged",
                    "category_norm": parsed["category_norm"],
                    "content_hash": new_hash,
                }
            },
        )
        return url, "unchanged"

    diffs = _diff(existing, parsed)
    await db["books"].update_one(
        {"_id": existing["_id"]},
        {"$set": {**parsed, **seen, "content_hash": new_hash, "raw_html": html, "last_status": "updated"}},
    )
    await db["changes"].insert_one(_change(parsed["upc"], "update", diffs, now))
    return url, "updated"


def _tally(summary: Dict[str, int], results: List[object]) -> None:
    for r in results:
        if isinstance(r, Exception):
            logger.error("Detail processing failed", exc_info=r)
            summary["failed"] += 1
            continue
        _, status = r
        summary[status if status in summary else "failed"] += 1


async def run_full_crawl(db: AsyncIOMotorDatabase) -> dict:
    # One client for the whole crawl, so connections to the site are pooled
    # instead of a new TLS handshake for each of the thousand book pages.
    async with get_http_client() as client:
        root_html = await fetch_text(settings.base_url, client=client)
        category_urls = parse_category_links(root_html, settings.base_url)
        logger.info("Discovered categories", extra={"count": len(category_urls)})

        # The cursor is only advanced once a category's books are stored, so an
        # interrupted crawl resumes at the first category it had not finished.
        state = await db["crawl_state"].find_one({"name": "full_crawl"})
        start_idx = int(state.get("category_index", 0)) if state else 0
        now = now_utc()
        state_fields = {"name": "full_crawl", "status": "running", "category_index": start_idx, "updated_at": now}
        if start_idx == 0 or not state:
            state_fields["started_at"] = now
        await db["crawl_state"].update_one({"name": "full_crawl"}, {"$set": state_fields}, upsert=True)

        sem = asyncio.Semaphore(settings.concurrency)
        summary = {"inserted": 0, "updated": 0, "unchanged": 0, "failed": 0}
        seen_urls: set[str] = set()
        for idx in range(start_idx, len(category_urls)):
            category_url = category_urls[idx]
            urls = [u for u in await _gather_all_detail_urls(category_url, client) if u not in seen_urls]
            seen_urls.update(urls)
            logger.info("Category URLs gathered", extra={"category": category_url, "books": len(urls), "index": idx})

            results = await asyncio.gather(*(_process_book(u, db, sem, client) for u in urls), return_exceptions=True)
            _tally(summary, results)

            await db["crawl_state"].update_one(
                {"name": "full_crawl"},
                {"$set": {"category_index": idx + 1, "updated_at": now_utc()}},
            )

    await db["crawl_state"].update_one(
        {"name": "full_crawl"},
        {"$set": {"status": "completed", "finished_at": now_utc(), "category_index": 0}},
    )

    logger.info("Crawl completed", extra=summary)
    return summary

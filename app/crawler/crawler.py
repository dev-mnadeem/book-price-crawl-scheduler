from __future__ import annotations

import asyncio
import logging
import random
from typing import Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.settings import settings
from app.analysis.significance import classify
from app.models.change import ChangeLog, FieldDiff
from app.utils.hashing import content_hash
from app.utils.text import normalize_category
from app.utils.http_client import fetch_text, get_http_client
from app.utils.time import now_utc
from .parser import parse_category_links, parse_listing_page, parse_book_detail

logger = logging.getLogger(__name__)


async def _gather_all_detail_urls(category_url: str) -> List[str]:
    client = get_http_client()
    try:
        page_url = category_url
        detail_urls: List[str] = []
        seen_pages: set[str] = set()
        while page_url and page_url not in seen_pages:
            seen_pages.add(page_url)
            html = await fetch_text(page_url, client=client)
            details, next_url = parse_listing_page(html, page_url)
            detail_urls.extend(details)
            page_url = next_url
        return list(dict.fromkeys(detail_urls))
    finally:
        await client.aclose()


def _diff(old: dict, new: dict) -> List[FieldDiff]:
    fields = [
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
    ]
    diffs: List[FieldDiff] = []
    for f in fields:
        if (old.get(f) or None) != (new.get(f) or None):
            diffs.append(FieldDiff(field=f, old=old.get(f), new=new.get(f)))
    return diffs


async def _process_book(url: str, db: AsyncIOMotorDatabase, sem: asyncio.Semaphore) -> Tuple[str, Optional[str]]:
    async with sem:
        client = get_http_client()
        try:
            html = await fetch_text(url, client=client)
            parsed = parse_book_detail(html, page_url=url, base_url=settings.base_url)
            if not parsed.get("upc"):
                logger.warning("Missing UPC, skipping", extra={"url": url})
                return url, "missing_upc"

            parsed["in_stock"] = bool((parsed.get("availability") or 0) > 0)
            parsed["currency"] = "GBP"  # site uses this currency
            # normalized category (lower-case) for stable filtering and hashing
            parsed["category_norm"] = normalize_category(parsed.get("category"))

            h_new = content_hash(parsed)
            now = now_utc()

            existing = await db["books"].find_one({"upc": parsed["upc"]})
            if not existing:
                doc = {
                    **parsed,
                    "content_hash": h_new,
                    "raw_html": html,
                    "first_seen": now,
                    "last_seen": now,
                    "crawl_timestamp": now,
                    "last_status": "inserted",
                }
                await db["books"].insert_one(doc)
                await db["changes"].insert_one(
                    ChangeLog(
                        book_upc=parsed["upc"],
                        change_type="new",
                        changes=[],
                        timestamp=now,
                        **classify([], "new").as_dict(),
                    ).model_dump()
                )
                return url, "inserted"
            else:
                existing_hash = existing.get("content_hash")
                # Compute the canonical hash for the existing document using the new scheme (migration-friendly)
                h_existing_current = content_hash(existing)
                if h_existing_current != h_new:
                    diffs = _diff(existing, parsed)
                    await db["books"].update_one(
                        {"_id": existing["_id"]},
                        {
                            "$set": {
                                **parsed,
                                "content_hash": h_new,
                                "raw_html": html,
                                "last_seen": now,
                                "crawl_timestamp": now,
                                "last_status": "updated",
                            }
                        },
                    )
                    await db["changes"].insert_one(
                        ChangeLog(
                            book_upc=parsed["upc"],
                            change_type="update",
                            changes=diffs,
                            timestamp=now,
                            **classify(diffs, "update").as_dict(),
                        ).model_dump()
                    )
                    return url, "updated"
                else:
                    # unchanged: ensure category_norm is set, and migrate content_hash to new scheme
                    set_fields = {
                        "last_seen": now,
                        "crawl_timestamp": now,
                        "last_status": "unchanged",
                        "category_norm": parsed.get("category_norm"),
                        "content_hash": h_new,
                    }
                    await db["books"].update_one({"_id": existing["_id"]}, {"$set": set_fields})
                    return url, "unchanged"
        finally:
            await client.aclose()


def _tally(summary: Dict[str, int], results: List[object]) -> None:
    for r in results:
        if isinstance(r, Exception):
            logger.error("Detail processing failed", exc_info=r)
            summary["failed"] += 1
            continue
        _, status = r
        summary[status if status in summary else "failed"] += 1


async def run_full_crawl(db: AsyncIOMotorDatabase) -> dict:
    client = get_http_client()
    try:
        root_html = await fetch_text(settings.base_url, client=client)
        category_urls = parse_category_links(root_html, settings.base_url)
    finally:
        await client.aclose()

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
        urls = [u for u in await _gather_all_detail_urls(category_url) if u not in seen_urls]
        seen_urls.update(urls)
        logger.info("Category URLs gathered", extra={"category": category_url, "books": len(urls), "index": idx})

        results = await asyncio.gather(*(_process_book(u, db, sem) for u in urls), return_exceptions=True)
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

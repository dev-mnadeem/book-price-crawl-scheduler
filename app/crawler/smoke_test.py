from __future__ import annotations

import asyncio
import logging
from typing import List

import orjson

from app.config.logging import setup_logging
from app.config.settings import settings
from app.crawler.parser import (
    parse_category_links,
    parse_listing_page,
    parse_book_detail,
)
from app.utils.hashing import content_hash
from app.utils.http_client import get_http_client, fetch_text

logger = logging.getLogger(__name__)


async def run() -> None:
    setup_logging(settings.log_level)
    client = get_http_client()
    try:
        print("=== Smoke test: fetching homepage ===")
        home_html = await fetch_text(settings.base_url, client=client)
        categories = parse_category_links(home_html, settings.base_url)
        print(f"Discovered {len(categories)} categories. Using first: {categories[0] if categories else 'N/A'}")
        if not categories:
            return

        category_url = categories[0]
        print("=== Fetching first category page ===")
        listing_html = await fetch_text(category_url, client=client)
        detail_urls, next_url = parse_listing_page(listing_html, category_url)
        print(f"Found {len(detail_urls)} book detail URLs on first page. Next page: {bool(next_url)}")

        sample_urls = detail_urls[:3]
        print(f"=== Sampling {len(sample_urls)} book detail pages ===")
        samples: List[dict] = []
        for u in sample_urls:
            html = await fetch_text(u, client=client)
            book = parse_book_detail(html, page_url=u, base_url=settings.base_url)
            book["content_hash"] = content_hash(book)
            samples.append(book)

        payload = {
            "category_url": category_url,
            "samples_count": len(samples),
            "samples": samples,
        }
        print(orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode())

    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(run())

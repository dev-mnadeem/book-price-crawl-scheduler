"""Run the crawler, locks and API against a real MongoDB.

The rest of the suite uses the in-memory FakeDB, which cannot run aggregation
pipelines or TTL indexes. These tests need MONGODB_TEST_URI and are skipped
without it:

    MONGODB_TEST_URI=mongodb://localhost:27017 pytest tests/test_mongo_integration.py
"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from pymongo import AsyncMongoClient

import app.crawler.crawler as crawler_mod
from app.api.main import app
from app.config.settings import settings
from app.crawler.crawler import run_full_crawl
from app.db.indexes import ensure_indexes
from app.db.locks import acquire_lock, release_lock
from app.db.mongo import get_db
from app.utils.time import now_utc

MONGO_URI = os.environ.get("MONGODB_TEST_URI")
pytestmark = pytest.mark.skipif(not MONGO_URI, reason="MONGODB_TEST_URI not set")

SITE = Path(__file__).resolve().parents[1] / "demo" / "site"
HOST = "http://fixture-site:8080/"


@pytest_asyncio.fixture()
async def mongo_db():
    client = AsyncMongoClient(MONGO_URI, tz_aware=True)
    db = client[f"books_monitor_test_{uuid.uuid4().hex[:8]}"]
    await ensure_indexes(db)
    try:
        yield db
    finally:
        await client.drop_database(db.name)
        await client.close()


@pytest.fixture()
def demo_site(monkeypatch):
    async def fetch_from_disk(url: str, client=None, max_retries=None) -> str:
        path = SITE / url.removeprefix(HOST)
        return (path / "index.html" if url.endswith("/") else path).read_text(encoding="utf-8")

    monkeypatch.setattr(crawler_mod, "fetch_text", fetch_from_disk)
    return lambda edition: monkeypatch.setattr(settings, "base_url", f"{HOST}{edition}/")


@pytest_asyncio.fixture()
async def api(mongo_db, api_key):
    async def override():
        return mongo_db

    app.dependency_overrides[get_db] = override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api", headers={"X-API-Key": api_key}) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_change_feed_after_two_demo_crawls(mongo_db, demo_site, api):
    demo_site("v1")
    await run_full_crawl(mongo_db)
    demo_site("v2")
    assert await run_full_crawl(mongo_db) == {"inserted": 1, "updated": 6, "unchanged": 1, "failed": 0}

    r = await api.get("/changes", params={"type": "update", "order": "severity"})
    assert r.status_code == 200
    severities = [c["severity"] for c in r.json()["items"]]
    assert severities == ["critical", "critical", "notable", "minor", "minor", "cosmetic"]

    r = await api.get("/changes", params={"min_severity": "notable", "type": "update"})
    assert {c["severity"] for c in r.json()["items"]} == {"critical", "notable"}
    assert r.json()["items"][0]["timestamp"].endswith("Z") or "+00:00" in r.json()["items"][0]["timestamp"]


@pytest.mark.asyncio
async def test_books_filters_paging_and_raw_detail(mongo_db, demo_site, api):
    demo_site("v1")
    await run_full_crawl(mongo_db)

    r = await api.get("/books", params={"category": "TRAVEL", "sort_by": "price", "order": "asc", "page_size": 2})
    body = r.json()
    assert body["total"] == 4
    assert [b["price_incl_tax"] for b in body["items"]] == [18.4, 20.0]

    params = {"category": "travel", "sort_by": "price", "order": "asc", "page": 2, "page_size": 2}
    page2 = await api.get("/books", params=params)
    assert [b["name"] for b in page2.json()["items"]] == ["The Cartographer's Holiday", "Salt Roads of the North"]

    r = await api.get("/books/demo000000000101", params={"include_raw": "true"})
    assert r.status_code == 200
    assert r.json()["content_hash"].startswith("sha256:")
    assert "<h1>Salt Roads of the North</h1>" in r.json()["raw_html"]

    assert (await api.get("/books/nope")).status_code == 404


@pytest.mark.asyncio
async def test_lock_is_exclusive_until_released_or_expired(mongo_db):
    assert await acquire_lock(mongo_db, "crawl_lock", owner="a")
    assert not await acquire_lock(mongo_db, "crawl_lock", owner="b")
    await release_lock(mongo_db, "crawl_lock", owner="a")
    assert await acquire_lock(mongo_db, "crawl_lock", owner="b")

    expired = now_utc() - timedelta(seconds=1)
    await mongo_db["locks"].update_one({"_id": "crawl_lock"}, {"$set": {"expires_at": expired}})
    assert await acquire_lock(mongo_db, "crawl_lock", owner="c")

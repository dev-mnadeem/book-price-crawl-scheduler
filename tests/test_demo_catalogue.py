"""Crawl the two demo editions end to end and check what the change feed says."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

import app.crawler.crawler as crawler_mod
from app.config.settings import settings as cfg
from app.crawler.crawler import run_full_crawl

SITE = Path(__file__).resolve().parents[1] / "demo" / "site"
HOST = "http://fixture-site:8080/"


@pytest.fixture()
def serve_demo_site(monkeypatch):
    async def fetch_from_disk(url: str, client=None, max_retries=None) -> str:
        path = SITE / url.removeprefix(HOST)
        if path.is_dir() or url.endswith("/"):
            path = path / "index.html"
        if not path.is_file():
            request = httpx.Request("GET", url)
            raise httpx.HTTPStatusError("404", request=request, response=httpx.Response(404, request=request))
        return path.read_text(encoding="utf-8")

    monkeypatch.setattr(crawler_mod, "fetch_text", fetch_from_disk)

    def use_edition(edition: str) -> None:
        monkeypatch.setattr(cfg, "base_url", f"{HOST}{edition}/")

    return use_edition


@pytest.mark.asyncio
async def test_v1_then_v2_produces_one_change_of_each_kind(fake_db, serve_demo_site):
    serve_demo_site("v1")
    assert await run_full_crawl(fake_db) == {"inserted": 7, "updated": 0, "unchanged": 0, "failed": 0}

    serve_demo_site("v2")
    assert await run_full_crawl(fake_db) == {"inserted": 1, "updated": 6, "unchanged": 1, "failed": 0}

    changes = [c async for c in fake_db["changes"].find({})]
    by_book = {c["book_upc"]: c for c in changes if c["change_type"] == "update"}

    assert by_book["demo000000000101"]["severity"] == "critical"  # price -30%
    assert by_book["demo000000000102"]["severity"] == "critical"  # sold out
    assert by_book["demo000000000201"]["severity"] == "notable"   # 15 -> 3 in stock
    assert by_book["demo000000000104"]["severity"] == "minor"     # price -2.5%
    assert by_book["demo000000000301"]["severity"] == "minor"     # rating and reviews
    assert by_book["demo000000000202"]["severity"] == "cosmetic"  # description wording

    new_titles = [c["book_upc"] for c in changes if c["change_type"] == "new"]
    assert "demo000000000105" in new_titles


from __future__ import annotations

import pytest

import app.crawler.crawler as crawler_mod
from app.crawler.crawler import run_full_crawl
from app.config.settings import settings as cfg
from app.utils import http_client


def html_root():
    return (
        """
        <html><body>
        <ul class="nav-list">
          <ul>
            <li><a href="/cat/travel/index.html">Travel</a></li>
            <li><a href="/cat/fiction/index.html">Fiction</a></li>
          </ul>
        </ul>
        </body></html>
        """
    )


def html_listing_travel(page: int = 1):
    next_link = '<li class="next"><a href="page-2.html">next</a></li>' if page == 1 else ""
    return f"""
    <html><body>
      <section>
        <article class="product_pod"><h3><a href="/book/b1.html">B1</a></h3></article>
        <article class="product_pod"><h3><a href="/book/b2.html">B2</a></h3></article>
      </section>
      <ul class="pager">{next_link}</ul>
    </body></html>
    """


def html_listing_fiction():
    return """
    <html><body>
      <section>
        <article class="product_pod"><h3><a href="/book/f1.html">F1</a></h3></article>
      </section>
    </body></html>
    """


def detail_page(upc: str, name: str, category: str, price_incl: float, price_excl: float, availability: int, rating: int, num_reviews: int):
    rating_class = {1:"One",2:"Two",3:"Three",4:"Four",5:"Five"}[rating]
    return f"""
    <html><body>
      <ul class="breadcrumb">
        <li><a href="/">Home</a></li>
        <li><a href="/books">Books</a></li>
        <li><a href="/cat/{category.lower()}">{category}</a></li>
        <li class="active">{name}</li>
      </ul>
      <div class="product_main">
        <h1>{name}</h1>
      </div>
      <p class="star-rating {rating_class}"></p>
      <div id="product_description"></div>
      <p>Nice book</p>
      <table class="table table-striped">
        <tr><th>UPC</th><td>{upc}</td></tr>
        <tr><th>Price (incl. tax)</th><td>£{price_incl:.2f}</td></tr>
        <tr><th>Price (excl. tax)</th><td>£{price_excl:.2f}</td></tr>
        <tr><th>Number of reviews</th><td>{num_reviews}</td></tr>
      </table>
      <p class="availability">In stock ({availability} available)</p>
      <div id="product_gallery"><img src="/media/{upc}.jpg"/></div>
    </body></html>
    """


@pytest.mark.asyncio
async def test_crawl_insert_update_and_resume(fake_db, monkeypatch):
    monkeypatch.setattr(cfg, "base_url", "http://site/")

    mapping = {
        "http://site/": html_root(),
        "http://site/cat/travel/index.html": html_listing_travel(1),
        "http://site/cat/travel/page-2.html": html_listing_travel(2),
        "http://site/cat/fiction/index.html": html_listing_fiction(),
        "http://site/book/b1.html": detail_page("UPC-B1", "Book 1", "Travel", 10.00, 9.00, 10, 4, 2),
        "http://site/book/b2.html": detail_page("UPC-B2", "Book 2", "Travel", 5.00, 4.50, 5, 2, 1),
        "http://site/book/f1.html": detail_page("UPC-F1", "Book F1", "Fiction", 7.00, 6.50, 3, 5, 4),
    }

    async def fake_fetch_text(url: str, client=None, max_retries=None) -> str:
        return mapping[url]

    # Patch the symbol used inside crawler module
    monkeypatch.setattr(crawler_mod, "fetch_text", fake_fetch_text, raising=False)

    # First run: insert all three
    summary1 = await run_full_crawl(fake_db)
    assert summary1["inserted"] == 3
    assert await fake_db["books"].count_documents({}) == 3

    # Change one detail (b1 price) and run again: expecting 1 update
    mapping["http://site/book/b1.html"] = detail_page("UPC-B1", "Book 1", "Travel", 11.00, 10.00, 10, 4, 2)
    summary2 = await run_full_crawl(fake_db)
    assert summary2["updated"] == 1

    # Resume scenario: set crawl_state to skip first category (i.e index=1 -> Fiction only)
    await fake_db["crawl_state"].update_one({"name": "full_crawl"}, {"$set": {"name": "full_crawl", "category_index": 1}}, upsert=True)
    # Reset mapping to original prices
    mapping["http://site/book/b1.html"] = detail_page("UPC-B1", "Book 1", "Travel", 10.00, 9.00, 10, 4, 2)
    mapping["http://site/book/b2.html"] = detail_page("UPC-B2", "Book 2", "Travel", 5.00, 4.50, 5, 2, 1)

    summary3 = await run_full_crawl(fake_db)
    # Only Fiction category processed; existing doc unchanged, so zero inserts/updates
    assert summary3["inserted"] == 0
    assert summary3["updated"] == 0

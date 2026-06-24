"""Parser tests against the saved demo catalogue in demo/site/."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.crawler.parser import parse_book_detail, parse_category_links, parse_listing_page, parse_price

SITE = Path(__file__).resolve().parents[1] / "demo" / "site" / "v1"
BASE = "http://demo/v1/"


def read(rel: str) -> str:
    return (SITE / rel).read_text(encoding="utf-8")


def test_category_links_skip_the_top_level_books_link():
    links = parse_category_links(read("index.html"), BASE)
    assert links == [
        "http://demo/v1/catalogue/category/books/travel_2/index.html",
        "http://demo/v1/catalogue/category/books/poetry_23/index.html",
        "http://demo/v1/catalogue/category/books/mystery_3/index.html",
    ]


def test_listing_page_resolves_relative_detail_links_and_next_page():
    url = BASE + "catalogue/category/books/travel_2/index.html"
    details, next_url = parse_listing_page(read("catalogue/category/books/travel_2/index.html"), url)
    assert details[0] == "http://demo/v1/catalogue/salt-roads-of-the-north_101/index.html"
    assert len(details) == 3
    assert next_url == "http://demo/v1/catalogue/category/books/travel_2/page-2.html"


def test_last_listing_page_has_no_next():
    url = BASE + "catalogue/category/books/travel_2/page-2.html"
    _, next_url = parse_listing_page(read("catalogue/category/books/travel_2/page-2.html"), url)
    assert next_url is None


def test_detail_page_fields():
    url = BASE + "catalogue/salt-roads-of-the-north_101/index.html"
    book = parse_book_detail(read("catalogue/salt-roads-of-the-north_101/index.html"), page_url=url, base_url=BASE)
    assert book == {
        "upc": "demo000000000101",
        "name": "Salt Roads of the North",
        "description": "A walking account of the old salt routes between the fjords and the inland markets.",
        "category": "Travel",
        "price_excl_tax": 40.0,
        "price_incl_tax": 40.0,
        "availability": 12,
        "num_reviews": 0,
        "image_url": "http://demo/media/cache/salt-roads-of-the-north_101.jpg",
        "rating": 4,
        "source_url": url,
    }


def test_out_of_stock_page_reads_as_zero_available():
    url = "http://demo/v2/catalogue/night-trains-to-anywhere_102/index.html"
    html = (SITE.parent / "v2/catalogue/night-trains-to-anywhere_102/index.html").read_text(encoding="utf-8")
    assert parse_book_detail(html, page_url=url, base_url=BASE)["availability"] == 0


@pytest.mark.parametrize(
    "text, expected",
    [("£51.77", 51.77), ("Â£51.77", 51.77), (" £1,204.00 ", 1204.0), ("", None), ("free", None), (None, None)],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected

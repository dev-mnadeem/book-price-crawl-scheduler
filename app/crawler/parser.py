from __future__ import annotations

import re
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup
from urllib.parse import urljoin

RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def parse_category_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []
    for a in soup.select("ul.nav-list ul li a"):
        href = a.get("href")
        if not href:
            continue
        links.append(urljoin(base_url, href))
    return links


def parse_listing_page(html: str, base_url: str) -> Tuple[List[str], Optional[str]]:
    """Return (detail_links, next_page_url)."""
    soup = BeautifulSoup(html, "lxml")
    detail_links: List[str] = []
    for a in soup.select("article.product_pod h3 a"):
        href = a.get("href")
        if not href:
            continue
        detail_links.append(urljoin(base_url, href))

    next_a = soup.select_one("li.next a")
    next_url = urljoin(base_url, next_a.get("href")) if next_a and next_a.get("href") else None
    return detail_links, next_url


def _parse_table(soup: BeautifulSoup) -> dict:
    data = {}
    for tr in soup.select("table.table.table-striped tr"):
        th = tr.find("th")
        td = tr.find("td")
        if not th or not td:
            continue
        data[th.text.strip()] = td.text.strip()
    return data


def parse_book_detail(html: str, page_url: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("div.product_main")

    name = main.find("h1").text.strip() if main else None

    # Rating
    rating = None
    rating_el = soup.select_one("p.star-rating")
    if rating_el:
        for cls in rating_el.get("class", []):
            if cls in RATING_MAP:
                rating = RATING_MAP[cls]
                break

    # Description
    description = None
    desc_header = soup.select_one("#product_description")
    if desc_header:
        p = desc_header.find_next_sibling("p")
        if p:
            description = p.text.strip()

    # Category from breadcrumb: Books > Category > Title
    category = None
    crumbs = soup.select("ul.breadcrumb li a")
    if len(crumbs) >= 2:
        # crumbs[0] = Home, crumbs[1] = Books, crumbs[2] = Category
        # On detail page, there are usually: Home, Books, Category, Title
        category = crumbs[-1].text.strip() if len(crumbs) >= 3 else None
        if len(crumbs) >= 3:
            category = crumbs[-1].text.strip()

    # Table fields
    table = _parse_table(soup)
    upc = table.get("UPC")
    price_incl = table.get("Price (incl. tax)")
    price_excl = table.get("Price (excl. tax)")
    num_reviews = table.get("Number of reviews")

    def parse_price(s: Optional[str]) -> Optional[float]:
        if not s:
            return None
        s = s.replace("£", "").strip()
        try:
            return float(s)
        except ValueError:
            return None

    price_incl_tax = parse_price(price_incl)
    price_excl_tax = parse_price(price_excl)

    # Availability: e.g. "In stock (22 available)"
    availability_text = soup.select_one("p.availability").text if soup.select_one("p.availability") else ""
    m = re.search(r"(\d+)", availability_text)
    availability = int(m.group(1)) if m else 0

    # Image url - join relative src against the actual page URL for correctness
    img_el = (
        soup.select_one("#product_gallery img")
        or soup.select_one("div.product_gallery img")
        or soup.select_one("div.item.active img")
        or soup.select_one("article.product_page img")
        or soup.select_one("div.product_page img")
        or soup.select_one("div.thumbnail img")
    )
    src = img_el.get("src") if img_el else None
    if not src:
        # fallback
        for img in soup.select("img[src]"):
            s = img.get("src")
            if s and "/media/" in s:
                src = s
                break
    image_url = urljoin(page_url, src) if src else None

    return {
        "upc": upc,
        "name": name,
        "description": description,
        "category": category,
        "price_excl_tax": price_excl_tax,
        "price_incl_tax": price_incl_tax,
        "availability": availability,
        "num_reviews": int(num_reviews) if num_reviews and num_reviews.isdigit() else 0,
        "image_url": image_url,
        "rating": rating,
        "source_url": page_url,
    }

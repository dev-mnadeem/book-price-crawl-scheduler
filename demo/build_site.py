"""Generate the offline demo catalogue in demo/site/.

The pages copy the markup of books.toscrape.com (nav-list, product_pod,
pager, product_main, the striped product table) so the real parser runs
against them unchanged, but every title, UPC and price is invented.

Two editions are written. v1 is the first crawl; v2 is the same shop a day
later with a price cut, a sell-out, a new title and a few small edits, so
that crawling v1 and then v2 produces one change of every severity.

Both editions are served from one host under /v1/ and /v2/. Image paths are
root-relative so a book's image_url, which is part of its content hash, is
the same in both editions; otherwise every book would look edited.

    python demo/build_site.py
"""

from __future__ import annotations

import html
from pathlib import Path

ROOT = Path(__file__).parent / "site"
PAGE_SIZE = 3
RATINGS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}

CATEGORIES = [("Travel", "travel_2"), ("Poetry", "poetry_23"), ("Mystery", "mystery_3")]

# slug, title, category, price, stock, rating, reviews, description
V1 = [
    ("salt-roads-of-the-north_101", "Salt Roads of the North", "Travel", 40.00, 12, 4, 0,
     "A walking account of the old salt routes between the fjords and the inland markets."),
    ("night-trains-to-anywhere_102", "Night Trains to Anywhere", "Travel", 18.40, 4, 3, 0,
     "Sleeper carriages, missed connections and the strangers met between them."),
    ("the-cartographers-holiday_103", "The Cartographer's Holiday", "Travel", 26.99, 7, 5, 1,
     "A mapmaker takes a month off and cannot stop correcting the tourist maps."),
    ("harbour-lights-and-ferries_104", "Harbour Lights and Ferries", "Travel", 20.00, 9, 2, 0,
     "Island hopping on the slow boats, one timetable at a time."),
    ("small-hours-sonnets_201", "Small Hours Sonnets", "Poetry", 13.50, 15, 4, 0,
     "Fourteen-line poems written between midnight and dawn."),
    ("weather-for-beginners_202", "Weather for Beginners", "Poetry", 31.20, 6, 3, 0,
     "Short poems about rain, fog and the forecasts that got it wrong."),
    ("the-locked-greenhouse_301", "The Locked Greenhouse", "Mystery", 22.75, 3, 5, 2,
     "A botanist is found inside a greenhouse locked from the inside."),
]

V2_CHANGES = {
    "salt-roads-of-the-north_101": {"price": 28.00},          # -30%: critical
    "night-trains-to-anywhere_102": {"stock": 0},            # sold out: critical
    "harbour-lights-and-ferries_104": {"price": 19.50},       # -2.5%: minor
    "small-hours-sonnets_201": {"stock": 3},                  # low stock: notable
    "weather-for-beginners_202": {"description": "Short poems about rain, fog and every forecast that got it wrong."},
    "the-locked-greenhouse_301": {"rating": 4, "reviews": 3},  # minor
}
V2_NEW = [
    ("a-lighthouse-in-winter_105", "A Lighthouse in Winter", "Travel", 24.10, 8, 4, 0,
     "Three months as the relief keeper on a rock in the North Atlantic."),
]


def upc_for(slug: str) -> str:
    return f"demo{slug.rsplit('_', 1)[1]:0>12}"


def page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"en-us\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)} | Books to Scrape (demo)</title></head>\n<body>\n{body}\n</body></html>\n"
    )


def index_page(prefix: str) -> str:
    links = "\n".join(
        f'      <li><a href="{prefix}catalogue/category/books/{path}/index.html">{name}</a></li>'
        for name, path in CATEGORIES
    )
    body = f"""<div class="side_categories">
  <ul class="nav nav-list">
    <li><a href="{prefix}catalogue/category/books_1/index.html">Books</a>
    <ul>
{links}
    </ul>
    </li>
  </ul>
</div>"""
    return page("All products", body)


def listing_page(books: list[tuple], page_no: int, pages: int, name: str) -> str:
    pods = []
    for slug, title, _cat, price, stock, rating, _rev, _desc in books:
        pods.append(f"""  <li class="col-xs-6 col-sm-4 col-md-3 col-lg-3">
    <article class="product_pod">
      <div class="image_container"><a href="../../../{slug}/index.html"><img src="/media/cache/{slug}.jpg" alt="{html.escape(title)}" class="thumbnail"></a></div>
      <p class="star-rating {RATINGS[rating]}"></p>
      <h3><a href="../../../{slug}/index.html" title="{html.escape(title)}">{html.escape(title)}</a></h3>
      <div class="product_price"><p class="price_color">£{price:.2f}</p><p class="instock availability">{"In stock" if stock else "Out of stock"}</p></div>
    </article>
  </li>""")
    pager = f'  <li class="current">Page {page_no} of {pages}</li>\n'
    if page_no > 1:
        prev = "index.html" if page_no == 2 else f"page-{page_no - 1}.html"
        pager = f'  <li class="previous"><a href="{prev}">previous</a></li>\n' + pager
    if page_no < pages:
        pager += f'  <li class="next"><a href="page-{page_no + 1}.html">next</a></li>\n'
    body = f"""<div class="page-header action"><h1>{name}</h1></div>
<section>
<ol class="row">
{chr(10).join(pods)}
</ol>
<ul class="pager">
{pager}</ul>
</section>"""
    return page(name, body)


def detail_page(book: tuple) -> str:
    slug, title, category, price, stock, rating, reviews, description = book
    cat_path = dict(CATEGORIES)[category]
    availability = f"In stock ({stock} available)" if stock else "Out of stock"
    body = f"""<ul class="breadcrumb">
  <li><a href="../../index.html">Home</a></li>
  <li><a href="../category/books_1/index.html">Books</a></li>
  <li><a href="../category/books/{cat_path}/index.html">{category}</a></li>
  <li class="active">{html.escape(title)}</li>
</ul>
<article class="product_page">
<div class="row">
  <div class="col-sm-6">
    <div id="product_gallery" class="carousel"><div class="thumbnail"><div class="carousel-inner">
      <div class="item active"><img src="/media/cache/{slug}.jpg" alt="{html.escape(title)}"></div>
    </div></div></div>
  </div>
  <div class="col-sm-6 product_main">
    <h1>{html.escape(title)}</h1>
    <p class="price_color">£{price:.2f}</p>
    <p class="instock availability"><i class="icon-ok"></i> {availability}</p>
    <p class="star-rating {RATINGS[rating]}"><i class="icon-star"></i></p>
  </div>
</div>
<div id="product_description" class="sub-header"><h2>Product Description</h2></div>
<p>{html.escape(description)}</p>
<div class="sub-header"><h2>Product Information</h2></div>
<table class="table table-striped">
  <tr><th>UPC</th><td>{upc_for(slug)}</td></tr>
  <tr><th>Product Type</th><td>Books</td></tr>
  <tr><th>Price (excl. tax)</th><td>£{price:.2f}</td></tr>
  <tr><th>Price (incl. tax)</th><td>£{price:.2f}</td></tr>
  <tr><th>Tax</th><td>£0.00</td></tr>
  <tr><th>Availability</th><td>{availability}</td></tr>
  <tr><th>Number of reviews</th><td>{reviews}</td></tr>
</table>
</article>"""
    return page(title, body)


def edition_v2() -> list[tuple]:
    fields = ["slug", "title", "category", "price", "stock", "rating", "reviews", "description"]
    books = []
    for book in V1:
        row = dict(zip(fields, book))
        row.update(V2_CHANGES.get(row["slug"], {}))
        books.append(tuple(row[f] for f in fields))
    return books + V2_NEW


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build(out: Path, books: list[tuple]) -> None:
    write(out / "index.html", index_page(""))
    for name, path in CATEGORIES:
        in_cat = [b for b in books if b[2] == name]
        pages = max(1, -(-len(in_cat) // PAGE_SIZE))
        for n in range(1, pages + 1):
            chunk = in_cat[(n - 1) * PAGE_SIZE : n * PAGE_SIZE]
            filename = "index.html" if n == 1 else f"page-{n}.html"
            write(out / "catalogue/category/books" / path / filename, listing_page(chunk, n, pages, name))
    for book in books:
        write(out / "catalogue" / book[0] / "index.html", detail_page(book))


if __name__ == "__main__":
    build(ROOT / "v1", V1)
    build(ROOT / "v2", edition_v2())
    print(f"wrote {sum(1 for _ in ROOT.rglob('*.html'))} pages to {ROOT}")

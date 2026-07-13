from __future__ import annotations

from fastapi import status


def _insert(loop, fake_db, doc):
    loop.run_until_complete(fake_db["books"].insert_one(doc))


def test_list_books_category_normalization(client, api_key, fake_db, event_loop):
    _insert(event_loop, fake_db, {
        "upc": "B1",
        "name": "Book 1",
        "category": "Travel",
        "category_norm": "travel",
        "price_incl_tax": 10.0,
        "rating": 3,
        "source_url": "http://x/1",
    })

    headers = {"X-API-Key": api_key}
    r = client.get("/books?category=travel", headers=headers)
    assert r.status_code == status.HTTP_200_OK
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["category_norm"] == "travel"


def test_list_books_sort_and_pagination(client, api_key, fake_db, event_loop):
    _insert(event_loop, fake_db, {
        "upc": "B2",
        "name": "Book 2",
        "category": "Travel",
        "category_norm": "travel",
        "price_incl_tax": 5.0,
        "rating": 5,
        "source_url": "http://x/2",
    })
    _insert(event_loop, fake_db, {
        "upc": "B3",
        "name": "Book 3",
        "category": "Travel",
        "category_norm": "travel",
        "price_incl_tax": 15.0,
        "rating": 2,
        "source_url": "http://x/3",
    })

    headers = {"X-API-Key": api_key}
    r = client.get("/books?category=Travel&sort_by=price&order=asc&page=1&page_size=1", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2
    assert data["page_size"] == 1
    assert data["items"][0]["upc"] == "B2"

    r2 = client.get("/books?category=Travel&sort_by=price&order=desc&page=1&page_size=1", headers=headers)
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["items"][0]["upc"] == "B3"


def test_get_book_by_id(client, api_key, fake_db, event_loop):
    _insert(event_loop, fake_db, {
        "upc": "B9",
        "name": "Book 9",
        "category": "Fiction",
        "category_norm": "fiction",
        "price_incl_tax": 9.0,
        "rating": 4,
        "source_url": "http://x/9",
        "raw_html": "<html></html>",
        "content_hash": "sha256:abc",
    })

    headers = {"X-API-Key": api_key}
    r = client.get("/books/B9", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["upc"] == "B9"
    assert "raw_html" not in data

    r2 = client.get("/books/B9?include_raw=true", headers=headers)
    assert r2.status_code == 200
    data2 = r2.json()
    assert "raw_html" in data2

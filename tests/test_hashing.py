from __future__ import annotations

from app.utils.hashing import content_hash


def test_content_hash_category_case_insensitive():
    base = {
        "name": "Book",
        "description": "A book",
        "category": "Travel",
        "price_excl_tax": 10.0,
        "price_incl_tax": 12.0,
        "availability": 5,
        "num_reviews": 3,
        "image_url": "http://example/img.jpg",
        "rating": 4,
    }

    a = dict(base)
    b = dict(base)
    b["category"] = "travel"

    assert content_hash(a) == content_hash(b)


def test_content_hash_changes_when_price_changes():
    base = {
        "name": "Book",
        "description": "A book",
        "category": "Travel",
        "price_excl_tax": 10.0,
        "price_incl_tax": 12.0,
        "availability": 5,
        "num_reviews": 3,
        "image_url": "http://example/img.jpg",
        "rating": 4,
    }
    a = dict(base)
    b = dict(base)
    b["price_incl_tax"] = 13.0

    assert content_hash(a) != content_hash(b)

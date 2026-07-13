from __future__ import annotations

from fastapi import status
from app.config.settings import settings


def test_auth_required(client):
    r = client.get("/books")
    assert r.status_code == status.HTTP_401_UNAUTHORIZED


def test_auth_ok_and_rate_limit(client, api_key, fake_db, event_loop):
    event_loop.run_until_complete(fake_db["books"].insert_one(
        {
            "upc": "X1",
            "name": "T1",
            "category": "Travel",
            "category_norm": "travel",
            "price_incl_tax": 10.0,
            "rating": 3,
            "source_url": "http://x",
        }
    ))

    headers = {"X-API-Key": api_key}

    # Lowering the rate limit to make test quick

    settings.rate_limit_per_hour = 2

    r1 = client.get("/books", headers=headers)
    assert r1.status_code == 200
    r2 = client.get("/books", headers=headers)
    assert r2.status_code == 200
    r3 = client.get("/books", headers=headers)
    assert r3.status_code == status.HTTP_429_TOO_MANY_REQUESTS

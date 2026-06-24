from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import status


def _insert(loop, fake_db, doc):
    loop.run_until_complete(fake_db["changes"].insert_one(doc))


def test_list_changes_basic_and_filters(client, api_key, fake_db, event_loop):
    now = datetime.now(timezone.utc)
    ch1 = {"book_upc": "U1", "change_type": "new", "changes": [], "timestamp": now - timedelta(hours=2)}
    ch2 = {"book_upc": "U2", "change_type": "update", "changes": [], "timestamp": now - timedelta(hours=1)}
    ch3 = {"book_upc": "U3", "change_type": "update", "changes": [], "timestamp": now}

    _insert(event_loop, fake_db, ch1)
    _insert(event_loop, fake_db, ch2)
    _insert(event_loop, fake_db, ch3)

    headers = {"X-API-Key": api_key}

    # Basic listing returns items sorted by timestamp desc
    r = client.get("/changes?limit=10", headers=headers)
    assert r.status_code == status.HTTP_200_OK
    data = r.json()
    assert data["count"] == 3
    assert data["items"][0]["book_upc"] == "U3"

    # Filter by type=update
    r2 = client.get("/changes?type=update", headers=headers)
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["count"] == 2
    assert all(item["change_type"] == "update" for item in data2["items"])

    # Filter by since (should exclude the oldest one)
    since_iso = (now - timedelta(hours=90/60)).isoformat()
    r3 = client.get(f"/changes?since={since_iso}", headers=headers)
    assert r3.status_code == 200
    data3 = r3.json()
    # since ~1.5h ago => should include last two
    assert data3["count"] == 2


def test_an_unparseable_since_is_rejected(client, api_key):
    r = client.get("/changes?since=yesterday", headers={"X-API-Key": api_key})
    assert r.status_code == 422
    assert "since" in r.json()["detail"]


def test_a_naive_since_is_read_as_utc(client, api_key, fake_db, event_loop):
    now = datetime.now(timezone.utc)
    _insert(event_loop, fake_db, {"book_upc": "OLD", "change_type": "new", "changes": [], "timestamp": now - timedelta(days=2)})
    _insert(event_loop, fake_db, {"book_upc": "NEW", "change_type": "new", "changes": [], "timestamp": now})

    naive = (now - timedelta(days=1)).replace(tzinfo=None).isoformat()
    r = client.get(f"/changes?since={naive}", headers={"X-API-Key": api_key})
    assert r.status_code == 200
    assert [item["book_upc"] for item in r.json()["items"]] == ["NEW"]

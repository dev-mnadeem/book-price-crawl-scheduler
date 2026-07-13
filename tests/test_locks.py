from __future__ import annotations

import asyncio
import pytest

from app.db.locks import acquire_lock, release_lock
from tests.utils.fake_db import FakeDB


@pytest.mark.asyncio
async def test_lock_acquisition_and_release():
    db = FakeDB()

    got1 = await acquire_lock(db, "crawl_lock", owner="t1")
    assert got1 is True

    got2 = await acquire_lock(db, "crawl_lock", owner="t2")
    assert got2 is False

    await release_lock(db, "crawl_lock", owner="t1")
    got3 = await acquire_lock(db, "crawl_lock", owner="t2")
    assert got3 is True


@pytest.mark.asyncio
async def test_lock_race_only_one_wins():
    db = FakeDB()

    async def contender(owner: str):
        return await acquire_lock(db, "crawl_lock", owner=owner)

    results = await asyncio.gather(contender("a"), contender("b"))
    assert sum(1 for r in results if r) == 1

from __future__ import annotations

import pytest

import app.scheduler.main as scheduler_mod
from app.db.locks import acquire_lock


@pytest.fixture()
def crawl_calls(fake_db, monkeypatch, tmp_path):
    calls: list[str] = []

    async def fake_get_db():
        return fake_db

    async def fake_crawl(db):
        calls.append("crawl")
        return {"inserted": 0, "updated": 0, "unchanged": 0, "failed": 0}

    monkeypatch.setattr(scheduler_mod, "get_db", fake_get_db)
    monkeypatch.setattr(scheduler_mod, "run_full_crawl", fake_crawl)
    monkeypatch.setattr(scheduler_mod.settings, "report_dir", str(tmp_path))
    return calls


@pytest.mark.asyncio
async def test_startup_run_waits_for_a_crawl_already_holding_the_lock(fake_db, crawl_calls):
    assert await acquire_lock(fake_db, scheduler_mod.LOCK_NAME, owner="runner")

    await scheduler_mod.job(owner="initial")

    assert crawl_calls == []
    lock = await fake_db["locks"].find_one({"_id": scheduler_mod.LOCK_NAME})
    assert lock["owner"] == "runner"


@pytest.mark.asyncio
async def test_job_crawls_writes_a_report_and_releases_the_lock(fake_db, crawl_calls, tmp_path):
    await scheduler_mod.job(owner="scheduler")

    assert crawl_calls == ["crawl"]
    assert len(list(tmp_path.glob("*.json"))) == 1
    lock = await fake_db["locks"].find_one({"_id": scheduler_mod.LOCK_NAME})
    assert lock["locked"] is False


def test_interval_setting_takes_precedence_over_cron(monkeypatch):
    monkeypatch.setattr(scheduler_mod.settings, "scheduler_interval_seconds", 600)
    monkeypatch.setattr(scheduler_mod.settings, "scheduler_run_on_start", False)
    scheduler = scheduler_mod.build_scheduler()
    jobs = scheduler.get_jobs()
    assert [j.id for j in jobs] == ["crawl_job"]
    assert jobs[0].trigger.interval.total_seconds() == 600

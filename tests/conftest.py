from __future__ import annotations

import sys
import os
import asyncio
import uuid
import pytest
from fastapi.testclient import TestClient

# Ensure project root on PYTHONPATH for 'app' imports when running pytest
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.api.main import app
from app.config.settings import settings
from app.db.mongo import get_db
from tests.utils.fake_db import FakeDB


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
def fake_db() -> FakeDB:
    return FakeDB()


@pytest.fixture(autouse=True)
def disable_scheduler():
    # prevent scheduler from starting during tests
    settings.run_scheduler_in_api = False
    yield


@pytest.fixture(autouse=True)
def reset_rate_limit_setting():
    # Rate limit extended for testing
    old = settings.rate_limit_per_hour
    settings.rate_limit_per_hour = 100
    yield
    settings.rate_limit_per_hour = old


@pytest.fixture()
def api_key(monkeypatch) -> str:
    # Provide a unique test API key per test to avoid rate limiter cross-test influence
    key = f"test-{uuid.uuid4()}"
    settings.api_keys = f"{settings.api_keys},{key}"
    # Reset token bucket for this key if exists
    try:
        from app.utils import rate_limiter as rl
        rl._buckets.pop(key, None)  # type: ignore[attr-defined]
    except Exception:
        pass
    return key


@pytest.fixture()
def test_app(fake_db: FakeDB, event_loop):
    async def _override_get_db():
        return fake_db

    # Override FastAPI dependency
    app.dependency_overrides[get_db] = _override_get_db

    # Also monkeypatch the module-level get_db used in startup events
    import app.api.main as api_main

    original_get_db = api_main.get_db
    api_main.get_db = _override_get_db  # type: ignore[assignment]
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_db, None)
        api_main.get_db = original_get_db  # type: ignore[assignment]


@pytest.fixture()
def client(test_app):
    return TestClient(test_app)

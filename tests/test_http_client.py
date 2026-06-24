from __future__ import annotations

import httpx
import pytest

from app.utils import http_client
from app.utils.http_client import fetch_text


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def instant(_delay):
        return None

    monkeypatch.setattr(http_client.asyncio, "sleep", instant)


def client_returning(statuses: list[int]) -> tuple[httpx.AsyncClient, list[int]]:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = statuses[min(len(calls), len(statuses) - 1)]
        calls.append(status)
        return httpx.Response(status, text=f"body {status}")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), calls


@pytest.mark.asyncio
async def test_server_errors_are_retried_until_success():
    client, calls = client_returning([503, 429, 200])
    async with client:
        assert await fetch_text("http://site/page", client=client, max_retries=3) == "body 200"
    assert calls == [503, 429, 200]


@pytest.mark.asyncio
async def test_not_found_fails_fast_without_retrying():
    client, calls = client_returning([404])
    async with client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_text("http://site/missing", client=client, max_retries=3)
    assert calls == [404]


@pytest.mark.asyncio
async def test_gives_up_after_the_retry_budget():
    client, calls = client_returning([500])
    async with client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_text("http://site/broken", client=client, max_retries=2)
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_transport_errors_are_retried():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.RemoteProtocolError("connection dropped", request=request)
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_text("http://site/flaky", client=client, max_retries=1) == "ok"
    assert attempts == 2

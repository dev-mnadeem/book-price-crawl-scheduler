from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


def _default_headers() -> dict[str, str]:
    return {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    }


def get_http_client() -> httpx.AsyncClient:
    timeout = httpx.Timeout(settings.request_timeout)
    client = httpx.AsyncClient(timeout=timeout, headers=_default_headers(), follow_redirects=True)
    return client


async def fetch_text(url: str, client: Optional[httpx.AsyncClient] = None, *, max_retries: Optional[int] = None) -> str:
    retries = max_retries if max_retries is not None else settings.max_retries
    own_client = False
    if client is None:
        client = get_http_client()
        own_client = True

    try:
        for attempt in range(retries + 1):
            try:
                resp = await client.get(url)
                status = resp.status_code
                if status >= 500 or status == 429:
                    raise httpx.HTTPStatusError("server error", request=resp.request, response=resp)
                resp.raise_for_status()
                return resp.text
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.HTTPStatusError) as e:
                if attempt >= retries:
                    logger.warning("HTTP request failed after retries", extra={"url": url, "error": str(e)})
                    raise
                delay = min(2 ** attempt + random.random(), 10.0)
                await asyncio.sleep(delay)
    finally:
        if own_client:
            await client.aclose()

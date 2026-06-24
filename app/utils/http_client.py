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
    return httpx.AsyncClient(timeout=timeout, headers=_default_headers(), follow_redirects=True)


def _is_retryable_status(status: int) -> bool:
    return status == 429 or status >= 500


async def fetch_text(url: str, client: Optional[httpx.AsyncClient] = None, *, max_retries: Optional[int] = None) -> str:
    retries = max_retries if max_retries is not None else settings.max_retries
    if retries < 0:
        raise ValueError("max_retries must be zero or more")
    own_client = False
    if client is None:
        client = get_http_client()
        own_client = True

    try:
        for attempt in range(retries + 1):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError as e:
                # A 404 or 403 will not fix itself on the next attempt; only
                # throttling and server-side failures are worth waiting out.
                if not _is_retryable_status(e.response.status_code) or attempt >= retries:
                    logger.warning("HTTP request failed", extra={"url": url, "status": e.response.status_code})
                    raise
            except httpx.TransportError as e:
                if attempt >= retries:
                    logger.warning("HTTP request failed after retries", extra={"url": url, "error": str(e)})
                    raise
            await asyncio.sleep(min(2**attempt + random.random(), 10.0))
    finally:
        if own_client:
            await client.aclose()

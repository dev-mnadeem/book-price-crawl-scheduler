from __future__ import annotations

import asyncio
import time
from typing import Dict

from fastapi import HTTPException, status

from app.config.settings import settings


class TokenBucket:
    def __init__(self, capacity: int, refill_rate_per_sec: float) -> None:
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate_per_sec
        self.last_refill = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        refill = elapsed * self.refill_rate
        if refill > 0:
            self.tokens = min(self.capacity, self.tokens + refill)
            self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


_buckets: Dict[str, TokenBucket] = {}
_lock = asyncio.Lock()


async def rate_limit(api_key: str) -> None:
    capacity = max(1, settings.rate_limit_per_hour)
    refill_rate = capacity / 3600.0
    async with _lock:
        bucket = _buckets.get(api_key)
        if bucket is None:
            bucket = TokenBucket(capacity=capacity, refill_rate_per_sec=refill_rate)
            _buckets[api_key] = bucket
        if not bucket.allow():
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

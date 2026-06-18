from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from time import monotonic, time

import redis.asyncio as redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.shared.config import settings


class DistributedRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._redis: redis.Redis | None = None
        if settings.app_env in {"staging", "production"}:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)

    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled or request.url.path.endswith("/health"):
            return await call_next(request)

        identity = request.headers.get("X-Identity-Id")
        credential = request.headers.get("Authorization")
        raw_key = identity or credential or (request.client.host if request.client else "unknown")
        key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        if self._redis is not None:
            limited = await self._is_redis_limited(key)
        else:
            limited = self._is_memory_limited(key)
        if limited:
            return self._limited_response()
        return await call_next(request)

    async def _is_redis_limited(self, key: str) -> bool:
        assert self._redis is not None
        window = settings.rate_limit_window_seconds
        bucket = int(time() // window)
        redis_key = f"rate-limit:{bucket}:{key}"
        try:
            count = await self._redis.incr(redis_key)
            if count == 1:
                await self._redis.expire(redis_key, window + 1)
            return count > settings.rate_limit_requests
        except redis.RedisError:
            # Availability is preferable to a global outage if Redis is briefly
            # unavailable. The per-process limiter remains a safety net.
            return self._is_memory_limited(key)

    def _is_memory_limited(self, key: str) -> bool:
        now = monotonic()
        window_start = now - settings.rate_limit_window_seconds
        hits = self._hits[key]
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= settings.rate_limit_requests:
            return True
        hits.append(now)
        return False

    @staticmethod
    def _limited_response() -> JSONResponse:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(settings.rate_limit_window_seconds)},
            content={
                "error": {
                    "code": "rate_limited",
                    "message": "Too many requests",
                }
            },
        )


# Compatibility alias for deployments importing the previous middleware name.
InMemoryRateLimitMiddleware = DistributedRateLimitMiddleware

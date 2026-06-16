from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled or request.url.path.endswith("/health"):
            return await call_next(request)

        key = request.headers.get("Authorization")
        if not key:
            key = request.client.host if request.client else "unknown"
        now = monotonic()
        window_start = now - settings.rate_limit_window_seconds
        hits = self._hits[key]
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= settings.rate_limit_requests:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests",
                    }
                },
            )
        hits.append(now)
        return await call_next(request)

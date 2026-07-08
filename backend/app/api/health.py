"""Liveness and readiness endpoints.

- ``GET /api/v1/health`` — liveness, always 200 (process is up).
- ``GET /api/v1/ready`` — readiness; DB is required, Redis is optional and only
  degrades the response (Redis is optional in Phase 0).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.core.db import ping_database
from app.shared.responses import success

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _ping_redis() -> bool:
    settings = get_settings()
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=1)
        try:
            await client.ping()
            return True
        finally:
            await client.aclose()
    except Exception:
        return False


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    settings = get_settings()
    return success(
        {
            "status": "ok",
            "service": settings.app_name,
            "env": settings.app_env,
        }
    )


@router.get("/ready", summary="Readiness probe")
async def ready(response: Response) -> dict:
    db_ok = await ping_database()
    redis_ok = await _ping_redis()

    # DB is required; Redis is optional and only marks the service degraded.
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall = "unavailable"
    elif not redis_ok:
        overall = "degraded"
    else:
        overall = "ready"

    return success(
        {
            "status": overall,
            "checks": {
                "database": "ok" if db_ok else "down",
                "redis": "ok" if redis_ok else "down (optional)",
            },
        }
    )

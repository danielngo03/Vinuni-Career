from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.infra.cache.memory import MemoryCache
from app.infra.cache.protocols import CacheClient
from app.infra.cache.redis_cache import RedisCache


@lru_cache
def get_cache() -> CacheClient:
    if settings.cache_backend == "redis":
        return RedisCache(settings.redis_url)
    return MemoryCache()

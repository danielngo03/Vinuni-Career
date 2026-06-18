from __future__ import annotations

from functools import lru_cache

from app.platform.cache.memory import MemoryCache
from app.platform.cache.protocols import CacheClient
from app.platform.cache.redis_cache import RedisCache
from app.shared.config import settings


@lru_cache
def get_cache() -> CacheClient:
    if settings.cache_backend == "redis":
        return RedisCache(settings.redis_url)
    return MemoryCache()

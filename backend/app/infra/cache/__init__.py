from app.infra.cache.factory import get_cache
from app.infra.cache.protocols import CacheClient

__all__ = ["CacheClient", "get_cache"]

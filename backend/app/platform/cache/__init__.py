"""app/platform/cache — Redis/memory cache. Canonical location."""
from __future__ import annotations

from app.platform.cache.factory import get_cache

__all__ = ["get_cache"]

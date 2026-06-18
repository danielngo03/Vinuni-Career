from __future__ import annotations

from dataclasses import dataclass
from time import monotonic


@dataclass
class CacheEntry:
    value: str
    expires_at: float | None


class MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if not entry:
            return None
        if entry.expires_at is not None and entry.expires_at <= monotonic():
            self._store.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        expires_at = monotonic() + ttl_seconds if ttl_seconds else None
        self._store[key] = CacheEntry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

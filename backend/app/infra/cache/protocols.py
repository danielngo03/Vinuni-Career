from __future__ import annotations

from typing import Protocol


class CacheClient(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...

    def delete(self, key: str) -> None: ...

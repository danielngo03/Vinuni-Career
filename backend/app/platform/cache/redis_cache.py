from __future__ import annotations

from redis import Redis


class RedisCache:
    def __init__(self, url: str) -> None:
        self._client = Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> str | None:
        value = self._client.get(key)
        return str(value) if value is not None else None

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self._client.set(name=key, value=value, ex=ttl_seconds)

    def delete(self, key: str) -> None:
        self._client.delete(key)

"""Message bus abstraction: in-process (default) + optional Redis fan-out.

``InProcessBus`` dispatches directly to the local connection manager — correct for a
single worker (local dev, no Docker/Redis). ``RedisBus`` publishes to Redis Pub/Sub and
runs a subscriber task that forwards received events to the local manager, so multiple
workers each deliver to their own sockets. Redis is imported lazily so the dependency is
optional; if it is unavailable we fall back to in-process.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

Dispatcher = Callable[[str, dict], Awaitable[None]]

# Every messaging event travels on one wrapping Redis channel; the logical channel
# (``user:{id}`` / ``org:{id}``) is inside the payload so one SUBSCRIBE covers all.
_WRAP_CHANNEL = "messaging:events"


class InProcessBus:
    def __init__(self) -> None:
        self._dispatch: Dispatcher | None = None

    def set_dispatcher(self, dispatch: Dispatcher) -> None:
        self._dispatch = dispatch

    async def publish(self, channel: str, event: dict) -> None:
        if self._dispatch is not None:
            await self._dispatch(channel, event)

    async def start(self) -> None:  # pragma: no cover - nothing to start
        return None

    async def stop(self) -> None:  # pragma: no cover
        return None


class RedisBus:
    def __init__(self, url: str) -> None:
        self._url = url
        self._dispatch: Dispatcher | None = None
        self._redis: Any = None
        self._pubsub: Any = None
        self._task: asyncio.Task[None] | None = None

    def set_dispatcher(self, dispatch: Dispatcher) -> None:
        self._dispatch = dispatch

    async def start(self) -> None:
        try:
            import redis.asyncio as aioredis  # type: ignore
        except Exception:  # noqa: BLE001
            logger.warning("redis not installed; messaging realtime falls back in-process")
            return
        self._redis = aioredis.from_url(self._url)
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(_WRAP_CHANNEL)
        self._task = asyncio.create_task(self._reader())

    async def _reader(self) -> None:  # pragma: no cover - needs a live Redis
        assert self._pubsub is not None
        async for message in self._pubsub.listen():
            if message is None or message.get("type") != "message":
                continue
            try:
                wrapped = json.loads(message["data"])
                channel = wrapped["channel"]
                event = wrapped["event"]
            except Exception:  # noqa: BLE001
                continue
            if self._dispatch is not None:
                await self._dispatch(channel, event)

    async def publish(self, channel: str, event: dict) -> None:
        if self._redis is None:
            # Redis unavailable — degrade to local dispatch so single worker still works.
            if self._dispatch is not None:
                await self._dispatch(channel, event)
            return
        await self._redis.publish(
            _WRAP_CHANNEL, json.dumps({"channel": channel, "event": event})
        )

    async def stop(self) -> None:  # pragma: no cover
        if self._task is not None:
            self._task.cancel()
        if self._pubsub is not None:
            await self._pubsub.close()
        if self._redis is not None:
            await self._redis.close()


def build_bus(redis_url: str | None) -> InProcessBus | RedisBus:
    return RedisBus(redis_url) if redis_url else InProcessBus()

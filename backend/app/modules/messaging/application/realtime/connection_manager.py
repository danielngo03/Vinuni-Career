"""In-memory registry of live WebSocket connections + channel subscriptions.

One process's live sockets. Cross-process fan-out is the bus's job (``hub``): the bus
delivers a published event to THIS process's manager, which forwards it to the local
sockets subscribed to the event's channel. Channels are ``user:{id}`` (personal) and
``org:{id}`` (shared org inbox). RBAC is re-checked at subscribe time (``ws.py``); the
manager only routes by channel string.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any


class Connection:
    __slots__ = ("send", "channels")

    def __init__(self, send: Any, channels: set[str]) -> None:
        self.send = send  # awaitable callable: (dict) -> None
        self.channels = channels


class ConnectionManager:
    def __init__(self) -> None:
        self._conns: set[Connection] = set()
        self._by_channel: dict[str, set[Connection]] = {}
        self._lock = asyncio.Lock()

    async def register(self, *, send: Any, channels: Iterable[str]) -> Connection:
        conn = Connection(send=send, channels=set(channels))
        async with self._lock:
            self._conns.add(conn)
            for ch in conn.channels:
                self._by_channel.setdefault(ch, set()).add(conn)
        return conn

    async def unregister(self, conn: Connection) -> None:
        async with self._lock:
            self._conns.discard(conn)
            for ch in conn.channels:
                bucket = self._by_channel.get(ch)
                if bucket is not None:
                    bucket.discard(conn)
                    if not bucket:
                        self._by_channel.pop(ch, None)

    async def dispatch_local(self, channel: str, event: dict) -> None:
        """Forward an event to every local socket subscribed to ``channel``."""

        async with self._lock:
            targets = list(self._by_channel.get(channel, ()))
        for conn in targets:
            try:
                await conn.send(event)
            except Exception:  # noqa: BLE001 - a dead socket must not break fan-out
                await self.unregister(conn)

    @property
    def local_connection_count(self) -> int:
        return len(self._conns)

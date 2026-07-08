"""Background-work queue interface with an inline local adapter.

Domain code enqueues work through :class:`TaskQueue`; it never imports Celery
directly. Locally (``BACKGROUND_WORKER_MODE=inline``) tasks run synchronously in
process. The same interface is later backed by Celery without changing callers
(``docs/ARCHITECTURE.md`` §4.5, ``docs/LOCAL_DEV_STACK.md``).

All tasks must be **idempotent** — safe to run more than once.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)

TaskHandler = Callable[[dict[str, Any]], Awaitable[None]]


class TaskQueue(Protocol):
    """Abstract enqueue interface."""

    def register(self, name: str, handler: TaskHandler) -> None: ...

    async def enqueue(self, name: str, payload: dict[str, Any]) -> None: ...


class InlineTaskQueue:
    """Runs registered handlers immediately in the current process.

    Used for Phase 0/1 local development and tests. Handlers must be idempotent
    so the behavior matches a real broker with at-least-once delivery.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, TaskHandler] = {}

    def register(self, name: str, handler: TaskHandler) -> None:
        self._handlers[name] = handler

    async def enqueue(self, name: str, payload: dict[str, Any]) -> None:
        handler = self._handlers.get(name)
        if handler is None:
            logger.warning("queue.no_handler", extra={"task": name})
            return
        await handler(payload)


_queue: TaskQueue | None = None


def get_queue() -> TaskQueue:
    """Return the process-wide queue chosen by ``BACKGROUND_WORKER_MODE``.

    Only the inline adapter is wired in Phase 0. The Celery adapter is added in a
    later phase behind this same interface.
    """

    global _queue
    if _queue is None:
        mode = get_settings().background_worker_mode
        # Celery adapter is a later-phase swap; inline is the Phase 0 default.
        if mode != "inline":
            logger.info(
                "queue.mode_fallback_inline",
                extra={"requested_mode": mode},
            )
        _queue = InlineTaskQueue()
    return _queue


def reset_queue() -> None:
    """Reset the cached queue (test helper)."""

    global _queue
    _queue = None

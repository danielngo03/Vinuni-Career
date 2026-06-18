"""
Domain event primitives and in-process event bus.

Rules:
- Domain events are immutable dataclasses.
- Modules emit events; other modules subscribe — never call each other directly.
- The InMemoryEventBus is used in tests and development.
- Production wires events through the transactional outbox (app.shared.outbox).
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events.

    Subclasses should declare additional fields with ``dataclass(frozen=True)``.
    """

    event_type: str
    aggregate_id: str
    aggregate_type: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


# Handler type: async callable receiving a DomainEvent
EventHandler = Callable[[DomainEvent], Coroutine[Any, Any, None]]


class EventBus:
    """Abstract event bus interface."""

    async def publish(self, event: DomainEvent) -> None:
        raise NotImplementedError

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    """Simple in-process pub/sub used in tests and local dev.

    Thread-safe for single-process asyncio apps.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        handlers = self._handlers.get(event.event_type, [])
        await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)

    def clear(self) -> None:
        """Reset subscriptions — useful in test teardown."""
        self._handlers.clear()


# Module-level singleton used when no DI container is wired.
_bus: EventBus = InMemoryEventBus()


def get_event_bus() -> EventBus:
    return _bus


def set_event_bus(bus: EventBus) -> None:
    global _bus  # noqa: PLW0603
    _bus = bus

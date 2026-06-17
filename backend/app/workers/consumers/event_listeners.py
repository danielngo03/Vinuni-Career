from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


EventHandler = Callable[[DomainEvent], None]


class EventListenerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def register(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def dispatch(self, event: DomainEvent) -> None:
        for handler in self._handlers.get(event.event_type, []):
            handler(event)


registry = EventListenerRegistry()

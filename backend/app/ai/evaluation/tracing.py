from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class AIOperationTrace:
    name: str
    metadata: dict[str, str] = field(default_factory=dict)
    start_time: float = field(default_factory=perf_counter)
    events: list[dict[str, str | float]] = field(default_factory=list)

    def add_event(self, event: str, **payload: str | float) -> None:
        self.events.append({"event": event, "elapsed_ms": self.elapsed_ms(), **payload})

    def elapsed_ms(self) -> float:
        return round((perf_counter() - self.start_time) * 1000, 3)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "metadata": self.metadata,
            "elapsed_ms": self.elapsed_ms(),
            "events": self.events,
        }

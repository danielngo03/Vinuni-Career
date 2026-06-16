from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SearchDocument:
    id: str
    entity_type: str
    title: str
    body: str
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None


@dataclass(frozen=True)
class SearchHit:
    document: SearchDocument
    score: float
    reasons: dict


class SearchClient(Protocol):
    def index(self, document: SearchDocument) -> None: ...

    def search(
        self,
        query: str,
        *,
        entity_type: str | None = None,
        embedding: list[float] | None = None,
        limit: int = 10,
    ) -> list[SearchHit]: ...

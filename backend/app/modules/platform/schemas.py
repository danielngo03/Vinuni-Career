from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1_000)
    entity_type: str | None = Field(default=None, max_length=50)
    limit: int = Field(default=10, ge=1, le=50)


class SearchResult(BaseModel):
    id: str
    entity_type: str
    title: str
    score: float
    metadata: dict[str, Any]
    reasons: dict[str, Any]


class SearchResponse(BaseModel):
    results: list[SearchResult]

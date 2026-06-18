from __future__ import annotations

import math
import re

from app.platform.search.protocols import SearchDocument, SearchHit


class MemorySearchClient:
    def __init__(self) -> None:
        self._documents: dict[str, SearchDocument] = {}

    def index(self, document: SearchDocument) -> None:
        self._documents[document.id] = document

    def search(
        self,
        query: str,
        *,
        entity_type: str | None = None,
        embedding: list[float] | None = None,
        limit: int = 10,
    ) -> list[SearchHit]:
        query_terms = set(_terms(query))
        hits: list[SearchHit] = []
        for document in self._documents.values():
            if entity_type and document.entity_type != entity_type:
                continue
            doc_terms = set(_terms(f"{document.title} {document.body}"))
            keyword_score = len(query_terms & doc_terms) / max(1, len(query_terms))
            vector_score = _cosine(embedding, document.embedding)
            score = round((0.65 * keyword_score + 0.35 * vector_score) * 100, 4)
            if score > 0:
                hits.append(
                    SearchHit(
                        document=document,
                        score=score,
                        reasons={
                            "keyword": round(keyword_score, 6),
                            "vector": round(vector_score, 6),
                            "backend": "memory",
                        },
                    )
                )
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]


def _terms(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9+#.]+", text.lower())


def _cosine(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(item * item for item in left)) * math.sqrt(
        sum(item * item for item in right)
    )
    if denominator == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator

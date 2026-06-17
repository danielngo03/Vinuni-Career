from __future__ import annotations

from app.infra.search import get_search_client
from app.schemas.search import SearchRequest, SearchResponse, SearchResult
from app.services.ai_service import embed_text


def search_documents(payload: SearchRequest) -> SearchResponse:
    embedding = embed_text(payload.query)
    hits = get_search_client().search(
        payload.query,
        entity_type=payload.entity_type,
        embedding=embedding,
        limit=payload.limit,
    )
    return SearchResponse(
        results=[
            SearchResult(
                id=hit.document.id,
                entity_type=hit.document.entity_type,
                title=hit.document.title,
                score=hit.score,
                metadata=hit.document.metadata,
                reasons=hit.reasons,
            )
            for hit in hits
        ]
    )

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.gateway import RerankRequest, get_llm_gateway
from app.ai.gateway.errors import LLMGatewayError
from app.ai.retrieval.chunking import TextChunk, chunk_text
from app.ai.retrieval.rerank import RankedCandidate, lexical_rerank, reciprocal_rank_fusion
from app.platform.search import SearchDocument, SearchHit, get_search_client


@dataclass(frozen=True)
class RetrievalResult:
    id: str
    text: str
    score: float
    metadata: dict[str, Any]


def index_text(
    *,
    document_id: str,
    entity_type: str,
    title: str,
    text: str,
    metadata: dict[str, Any] | None = None,
    chunk_size: int = 1_200,
    overlap: int = 180,
) -> list[TextChunk]:
    """Chunk, embed, and index a document as independently retrievable passages."""
    gateway = get_llm_gateway()
    chunks = chunk_text(
        text,
        chunk_size=chunk_size,
        overlap=overlap,
        document_id=document_id,
    )
    search = get_search_client()
    for chunk in chunks:
        embedding = gateway.embed(chunk.text).embedding
        search.index(
            SearchDocument(
                id=chunk.chunk_id,
                entity_type=entity_type,
                title=title,
                body=chunk.text,
                embedding=embedding,
                metadata={
                    **(metadata or {}),
                    "document_id": document_id,
                    "chunk_index": chunk.index,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char,
                    "token_count": chunk.token_count,
                    "section": chunk.section,
                },
            )
        )
    return chunks


def hybrid_retrieve(
    query: str,
    *,
    entity_type: str | None = None,
    candidate_limit: int = 30,
    result_limit: int = 8,
) -> list[RetrievalResult]:
    """Retrieve with dense+sparse fusion and provider reranking.

    Search adapters provide the first hybrid candidate set. We derive two
    explicit rankings from their component scores, fuse them with RRF, then use
    the configured reranker. A deterministic lexical reranker is the fallback.
    """
    gateway = get_llm_gateway()
    embedding = gateway.embed(query).embedding
    hits = get_search_client().search(
        query,
        entity_type=entity_type,
        embedding=embedding,
        limit=candidate_limit,
    )
    if not hits:
        return []

    dense = _ranking(hits, "vector")
    sparse = _ranking(hits, "keyword")
    fused = reciprocal_rank_fusion([dense, sparse], limit=candidate_limit)
    by_id = {hit.document.id: hit for hit in hits}

    try:
        response = gateway.rerank(
            RerankRequest(
                query=query,
                documents=[candidate.text for candidate in fused],
                top_n=min(result_limit, len(fused)),
            )
        )
        ordered = [
            (fused[item.index], item.relevance_score)
            for item in response.results
            if 0 <= item.index < len(fused)
        ]
    except LLMGatewayError:
        ordered = [
            (candidate, candidate.score)
            for candidate in lexical_rerank(query, fused, limit=result_limit)
        ]

    return [
        RetrievalResult(
            id=candidate.id,
            text=candidate.text,
            score=round(float(score), 6),
            metadata={
                **by_id[candidate.id].document.metadata,
                **candidate.metadata,
            },
        )
        for candidate, score in ordered[:result_limit]
    ]


def _ranking(hits: list[SearchHit], reason: str) -> list[RankedCandidate]:
    ranked = sorted(
        hits,
        key=lambda hit: float(hit.reasons.get(reason, 0.0)),
        reverse=True,
    )
    return [
        RankedCandidate(
            id=hit.document.id,
            text=hit.document.body,
            score=float(hit.reasons.get(reason, hit.score)),
            metadata={"search_score": hit.score},
        )
        for hit in ranked
    ]

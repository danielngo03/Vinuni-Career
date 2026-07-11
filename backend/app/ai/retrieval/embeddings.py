"""Embedding helpers: get/cache embeddings, cosine similarity, batch chunking.

All embedding calls go through the AI gateway so the provider/model are never
exposed here. The ``embedding_cheap`` alias resolves to ``text-embedding-3-small``
via the gateway alias map — callers never see the concrete model name.

When pgvector is disabled (``PGVECTOR_ENABLED=false``) or real calls are off
(``AI_REAL_CALLS_ENABLED=false``), all functions fall back to offline/hash
embeddings so the rest of the system works without infrastructure.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from collections import OrderedDict
from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.ai.gateway.base import AIEmbedding
from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
from app.ai.observability.cost_estimator import estimate_cost_usd
from app.ai.observability.usage import log_ai_usage, log_ai_usage_async
from app.core.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_BATCH_SIZE = 512  # max texts per embed call (well below OpenRouter's 2048 limit)

# ---------------------------------------------------------------------------
# In-process LRU embedding cache
# Keyed by (alias, sha256(text)). No TTL — embeddings are stable once produced.
# Evicts oldest entries when capacity is exceeded (standard LRU behaviour).
# ---------------------------------------------------------------------------
_CACHE_MAX = 2000  # ~80 MB at 1536 dims × 4 bytes × 2000 ≈ 12 MB; generous headroom

_embed_cache: OrderedDict[str, list[float]] = OrderedDict()


def _cache_key(text: str, alias: str) -> str:
    digest = hashlib.sha256(f"{alias}:{text}".encode()).hexdigest()
    return digest


def _cache_get(key: str) -> list[float] | None:
    if key in _embed_cache:
        _embed_cache.move_to_end(key)
        return _embed_cache[key]
    return None


def _cache_put(key: str, vector: list[float]) -> None:
    _embed_cache[key] = vector
    _embed_cache.move_to_end(key)
    while len(_embed_cache) > _CACHE_MAX:
        _embed_cache.popitem(last=False)


def clear_embed_cache() -> None:
    """Clear the in-process embedding cache (useful in tests)."""
    _embed_cache.clear()


def cosine_sim(a: Sequence[float], b: Sequence[float]) -> float:
    """Return the cosine similarity in [-1, 1] between two equal-length vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


async def embed_texts(
    texts: list[str],
    *,
    alias: str | None = None,
    db: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
    task_type: str = "embedding",
) -> list[AIEmbedding]:
    """Return one embedding per text string, batching automatically.

    Args:
        texts: Input strings (empty strings produce a zero vector offline).
        alias: Gateway alias to use. Defaults to ``ai_embedding_model_alias``
               from settings (``embedding_cheap``).
        db: Optional async session. When provided, a real (non-cached) provider
            call writes a cost row to ``ai_usage_log`` so embedding spend is
            visible to the budget guard (spec §5.4). Without a session the call
            still emits the sync structured usage line.
        user_id: Optional user to attribute the embedding cost to.
        task_type: Usage-ledger label (e.g. ``"kb_embedding"``).

    Uses ``get_provider_for_alias`` so embeddings always route to the provider
    registered for the embedding alias, not the default chat provider.
    """
    settings = get_settings()
    resolved_alias = alias or settings.ai_embedding_model_alias

    # Route through the alias-specific provider (ADR-0011 §6).
    # Fall back to the offline provider when real calls are disabled.
    if real_provider_active():
        try:
            provider = get_provider_for_alias(resolved_alias)
        except Exception:
            from app.ai.gateway.offline import OfflineProvider

            provider = OfflineProvider()
    else:
        from app.ai.gateway.offline import OfflineProvider

        provider = OfflineProvider()

    results: list[AIEmbedding] = []
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []

    # Check cache for each input text before hitting the provider
    cached_vectors: list[list[float] | None] = []
    for text in texts:
        key = _cache_key(text, resolved_alias)
        cached_vectors.append(_cache_get(key))

    for i, vec in enumerate(cached_vectors):
        if vec is None:
            uncached_indices.append(i)
            uncached_texts.append(texts[i])

    # Fetch uncached texts in batches
    fetched: list[AIEmbedding] = []
    for i in range(0, len(uncached_texts), _BATCH_SIZE):
        batch = uncached_texts[i : i + _BATCH_SIZE]
        embeddings = await provider.embed(batch, alias=resolved_alias)
        fetched.extend(embeddings)
        # Populate cache
        for text, emb in zip(batch, embeddings, strict=True):
            _cache_put(_cache_key(text, resolved_alias), emb.vector)

    # Cost/usage ledger: only a real (non-cached) provider fetch spends money.
    # Cache hits and the offline provider are free and intentionally not logged.
    if uncached_texts and real_provider_active():
        prompt_chars = sum(len(t) for t in uncached_texts)
        if db is not None:
            await log_ai_usage_async(
                db,
                task_type=task_type,
                alias=resolved_alias,
                success=True,
                prompt_chars=prompt_chars,
                user_id=user_id,
                cost_usd=estimate_cost_usd(resolved_alias, prompt_chars=prompt_chars),
            )
        else:
            log_ai_usage(
                task_type=task_type,
                alias=resolved_alias,
                success=True,
                prompt_chars=prompt_chars,
            )

    # Reconstruct results in original order
    fetch_iter = iter(fetched)
    for i, _text in enumerate(texts):
        cached_vector = cached_vectors[i]
        if cached_vector is not None:
            results.append(AIEmbedding(vector=cached_vector, model_alias=resolved_alias))
        else:
            results.append(next(fetch_iter))

    return results


async def embed_single(text: str, *, alias: str | None = None) -> list[float]:
    """Convenience wrapper — returns the raw float vector for a single text."""
    embeddings = await embed_texts([text], alias=alias)
    return embeddings[0].vector if embeddings else []


def top_k_by_cosine(
    query_vector: Sequence[float],
    candidates: list[tuple[str, Sequence[float]]],
    *,
    k: int = 10,
    min_score: float = 0.0,
) -> list[tuple[str, float]]:
    """Rank candidates by cosine similarity to the query and return top-k.

    Args:
        query_vector: The embedding of the query text.
        candidates: List of ``(id, vector)`` pairs.
        k: Maximum results to return.
        min_score: Minimum cosine similarity to include.

    Returns:
        Sorted list of ``(id, score)`` tuples, highest score first.
    """
    scored = [(cid, cosine_sim(query_vector, vec)) for cid, vec in candidates]
    scored.sort(key=lambda t: -t[1])
    return [(cid, s) for cid, s in scored if s >= min_score][:k]

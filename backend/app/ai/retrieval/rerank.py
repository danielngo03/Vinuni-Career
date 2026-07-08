"""Cross-encoder reranker for retrieval results.

After BM25+vector hybrid search, a reranker scores each (query, document)
pair and re-orders the top candidates. This is more accurate than cosine
similarity alone because cross-encoders see both texts simultaneously.

Implementation strategy (three tiers, AI_PRODUCT_SPEC.md §6.3):
1. We use the AI gateway's configured ``rerank_model_alias`` as a listwise
   reranker via a single structured prompt. Admins can route this alias to
   OpenRouter, OpenAI, Azure-compatible endpoints, or local Ollama.
2. When no real provider is active (offline/local dev, or the LLM call
   fails/returns malformed output), fall back to ``local_reranker.local_rerank``
   — a free, zero-network, deterministic BM25-lite lexical rerank. This is a
   REAL reranking signal, not a no-op: it actually reorders candidates by
   lexical relevance instead of blindly preserving input order.
3. Absolute last resort (local rerank itself errors on malformed input):
   preserve original order with neutral descending scores.
- Input is capped at ``_MAX_RERANK`` candidates to control token cost.
- Provider, model, tokens, and internal scores are never returned to callers.

Usage:
    from app.ai.retrieval.rerank import rerank_jobs

    fused = await hybrid_job_search(session, query="ML engineer")
    job_ids = [jid for jid, _ in fused[:20]]
    docs = {jid: job_title_and_summary[jid] for jid in job_ids}
    reranked = await rerank_jobs(query="ML engineer", job_docs=docs, top_k=5)
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

from app.ai.gateway import runtime_config
from app.ai.gateway.base import AIMessage
from app.ai.gateway.factory import real_provider_active
from app.ai.gateway.task_runner import AiTaskRunner
from app.ai.retrieval.local_reranker import local_rerank
from app.ai.safety.input_guard import sanitize_instruction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_MAX_RERANK = 20  # cap to control token spend


async def rerank_jobs(
    query: str,
    job_docs: dict[uuid.UUID, str],
    *,
    top_k: int = 10,
    db: AsyncSession | None = None,
) -> list[tuple[uuid.UUID, float]]:
    """Rerank a set of job documents against a query using the AI gateway.

    Args:
        query: The user's search query.
        job_docs: Mapping of ``job_id → short text representation`` for reranking.
                  Text should be ≤ 200 chars (title + key skills) to stay token-cheap.
        top_k: Maximum results to return after reranking.
        db: Optional database session for budget checks and usage logging.

    Returns:
        List of ``(job_id, score)`` tuples sorted by descending relevance.
        Falls back to original order with equal scores if AI is unavailable.
    """
    if not job_docs:
        return []

    if not real_provider_active():
        # No real provider configured — use the free local lexical reranker
        # instead of blindly preserving input order (tier 2, §6.3).
        return local_rerank(query, job_docs, top_k=top_k)

    candidates = list(job_docs.items())[:_MAX_RERANK]

    # Build compact JSON for the prompt
    numbered: list[dict[str, int | str]] = [
        {"rank": i + 1, "id": str(jid), "text": text[:200]}
        for i, (jid, text) in enumerate(candidates)
    ]
    numbered_json = json.dumps(numbered, ensure_ascii=False)

    safe_query, _ = sanitize_instruction(query)
    safe_query = (safe_query or "")[:300]

    system_prompt = (
        "You are a job relevance ranker. Given a job search query and a list "
        "of job documents, output ONLY a JSON array of the document ranks in "
        "order from most relevant to least relevant. Example output: "
        "[3, 1, 5, 2, 4]. Output ONLY the JSON array, nothing else."
    )
    user_prompt = (
        f"Query: {safe_query}\n\n"
        f"Jobs:\n{numbered_json}\n\n"
        "Return a JSON array of the ranks from most relevant to least relevant."
    )

    try:
        alias = runtime_config.current().rerank_model_alias
        runner = AiTaskRunner(
            db,
            alias=alias,
            task_type="retrieval_rerank",
            tool_class="read_only",
        )
        completion = await runner.complete(
            [
                AIMessage(role="system", content=system_prompt),
                AIMessage(role="user", content=user_prompt),
            ],
            temperature=0.0,
            max_tokens=200,
        )
        # Parse the rank array from the response
        ranks: list[int] = _parse_rank_array(completion.text)
        if not isinstance(ranks, list):
            raise ValueError("not a list")
    except Exception:
        # LLM reranker degraded — fall back to the free local lexical
        # reranker rather than a naive pass-through (tier 2, §6.3).
        return local_rerank(query, dict(candidates), top_k=top_k)

    # Map ranks back to job IDs
    rank_to_item: dict[int, uuid.UUID] = {
        int(item["rank"]): uuid.UUID(str(item["id"])) for item in numbered
    }
    reranked: list[tuple[uuid.UUID, float]] = []
    seen: set[uuid.UUID] = set()
    for position, rank in enumerate(ranks):
        jid = rank_to_item.get(rank)
        if jid and jid not in seen:
            seen.add(jid)
            score = 1.0 / (position + 1)
            reranked.append((jid, score))

    # Append any candidates not mentioned in the rank output (preserve coverage)
    for jid, _ in candidates:
        if jid not in seen:
            reranked.append((jid, 0.0))

    return reranked[:top_k]


def _parse_rank_array(text: str) -> list[int]:
    """Parse a JSON array of integer ranks from model output."""

    raw = text.strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        raw = parts[1] if len(parts) > 1 else raw
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
    if "[" in raw and "]" in raw:
        raw = raw[raw.index("[") : raw.rindex("]") + 1]
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("rerank output must be a list")
    return [int(item) for item in parsed]


def rerank_kb_chunks(
    query: str,
    chunk_docs: dict[uuid.UUID, str],
    *,
    top_k: int = 5,
) -> list[tuple[uuid.UUID, float]]:
    """Rerank retrieved KB chunks against the query (AI_PRODUCT_SPEC.md §6.3).

    Always uses the free local lexical reranker (never the LLM tier) — KB
    result sets are small (already capped by hybrid retrieval) and calling an
    LLM to rerank ~10-20 short chunks on every single RAG query would spend
    real tokens for a step that doesn't need semantic reasoning: the hybrid
    dense+BM25 retrieval already did the semantic heavy lifting, this step
    only sharpens ordering among the already-relevant candidates.

    Args:
        query: The user's KB query text.
        chunk_docs: Mapping of ``chunk_id -> content`` (or a short excerpt)
            for the candidates returned by hybrid retrieval.
        top_k: Maximum number of chunks to keep after reranking.

    Returns:
        ``[(chunk_id, score)]`` sorted by descending lexical relevance.
    """
    return local_rerank(query, chunk_docs, top_k=top_k)

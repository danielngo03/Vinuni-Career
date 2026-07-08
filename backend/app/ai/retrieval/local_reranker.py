"""Local, free, offline lexical reranker (AI_PRODUCT_SPEC.md §6.3, tier 2).

Three-tier reranking strategy, in priority order:

  1. LLM-as-reranker via the AI gateway (``app.ai.retrieval.rerank``) — most
     accurate, costs tokens, requires a real provider to be configured.
  2. **THIS MODULE** — local BM25-lite lexical scoring. Zero cost, zero
     network, always available, deterministic. Used automatically whenever
     no real provider is active, or when the LLM reranker call fails.
  3. Pass-through (original order) — absolute last resort, only if this
     module itself receives malformed input.

No heavy ML dependency is added here on purpose (no ``sentence-transformers``/
``torch``/``transformers``). This project's local-dev stack is lightweight by
default (``docs/LOCAL_DEV_STACK.md``); a real transformer cross-encoder (e.g.
BGE-reranker-v2-m3 via Ollama, as sketched in AI_PRODUCT_SPEC.md §6.3) is a
legitimate later upgrade but needs an ADR before pulling in a multi-GB model
dependency — see the recommendation logged in
``docs/IMPLEMENTATION_STATUS.md``. Until then, this lexical tier is what
actually runs for every free/offline rerank in the system, so it is a real
component, not a placeholder.

Scoring: BM25 (Okapi) term-frequency scoring between the query and each
candidate's short text representation. This is a lexical signal, not a
semantic one — good at catching exact/near-exact keyword matches cheaply;
it does not understand synonyms or paraphrase the way a real cross-encoder
or LLM would.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_BM25_K1 = 1.5
_BM25_B = 0.75

# Candidate id type is generic (UUID for jobs/KB chunks, but any hashable id
# works) so callers get a precisely-typed return instead of a fixed Union —
# `rerank_jobs`/`rerank_kb_chunks` (both UUID-keyed) and any future str-keyed
# caller each get back exactly the id type they passed in. Declared as a PEP
# 695 type parameter directly on `local_rerank` below.


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(_normalize(text))


def _bm25_score(
    query_terms: Counter[str],
    doc_terms: Counter[str],
    doc_len: int,
    avg_doc_len: float,
) -> float:
    if doc_len == 0:
        return 0.0
    score = 0.0
    for term, qf in query_terms.items():
        tf = doc_terms.get(term, 0)
        if tf == 0:
            continue
        numerator = tf * (_BM25_K1 + 1)
        denominator = tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * (doc_len / (avg_doc_len or 1.0)))
        score += (numerator / denominator) * qf
    return score


def local_rerank[CandidateId](
    query: str,
    candidates: Mapping[CandidateId, str],
    *,
    top_k: int = 10,
) -> list[tuple[CandidateId, float]]:
    """Rerank ``candidates`` against ``query`` using local BM25-lite scoring.

    Args:
        query: The user's search/chat query text.
        candidates: Mapping of ``id -> short text representation`` (title,
            summary, or chunk content). Longer texts are fine; tokenization
            is O(n) and cheap.
        top_k: Maximum number of results to return.

    Returns:
        ``[(id, score)]`` sorted by descending BM25 score. ``score`` is a
        relative lexical relevance value (not calibrated to a fixed range —
        do not surface it to end users; it is an internal ranking signal
        only, per AI_PRODUCT_SPEC.md §9.2/§14 "never expose similarity
        scores").

        If ``query`` has no usable tokens (empty/whitespace), the original
        insertion order is preserved with neutral ``0.0`` scores rather than
        crashing or returning an arbitrary order.
    """
    if not candidates:
        return []

    query_terms = Counter(_tokenize(query))
    if not query_terms:
        return [(cid, 0.0) for cid in list(candidates)[:top_k]]

    doc_terms_map: dict[CandidateId, Counter[str]] = {}
    doc_lens: dict[CandidateId, int] = {}
    for cid, text in candidates.items():
        tokens = _tokenize(text)
        doc_terms_map[cid] = Counter(tokens)
        doc_lens[cid] = len(tokens)

    nonzero_lens = [n for n in doc_lens.values() if n > 0]
    avg_doc_len = (sum(nonzero_lens) / len(nonzero_lens)) if nonzero_lens else 1.0

    scored = [
        (cid, _bm25_score(query_terms, doc_terms_map[cid], doc_lens[cid], avg_doc_len))
        for cid in candidates
    ]
    scored.sort(key=lambda pair: -pair[1])
    return scored[:top_k]

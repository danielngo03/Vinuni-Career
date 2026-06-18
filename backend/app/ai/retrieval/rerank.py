from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RankedCandidate:
    id: str
    text: str
    score: float
    metadata: dict[str, str | float | int | bool] = field(default_factory=dict)


def reciprocal_rank_fusion(
    rankings: list[list[RankedCandidate]],
    *,
    k: int = 60,
    limit: int = 20,
) -> list[RankedCandidate]:
    fused_scores: dict[str, float] = {}
    candidates: dict[str, RankedCandidate] = {}
    for ranking in rankings:
        for rank, candidate in enumerate(ranking, start=1):
            fused_scores[candidate.id] = fused_scores.get(candidate.id, 0.0) + 1.0 / (k + rank)
            candidates.setdefault(candidate.id, candidate)
    return [
        RankedCandidate(
            id=candidate_id,
            text=candidates[candidate_id].text,
            score=round(score, 6),
            metadata={**candidates[candidate_id].metadata, "rrf_score": round(score, 6)},
        )
        for candidate_id, score in sorted(
            fused_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:limit]
    ]


def lexical_rerank(
    query: str,
    candidates: list[RankedCandidate],
    *,
    limit: int = 10,
) -> list[RankedCandidate]:
    query_terms = _weighted_terms(query)
    reranked = []
    for candidate in candidates:
        candidate_terms = _weighted_terms(candidate.text)
        lexical = _cosine_sparse(query_terms, candidate_terms)
        score = 0.65 * lexical + 0.35 * min(1.0, candidate.score)
        reranked.append(
            RankedCandidate(
                id=candidate.id,
                text=candidate.text,
                score=round(score, 6),
                metadata={
                    **candidate.metadata,
                    "lexical_cross_score": round(lexical, 6),
                    "pre_rerank_score": candidate.score,
                },
            )
        )
    return sorted(reranked, key=lambda item: item.score, reverse=True)[:limit]


def _weighted_terms(text: str) -> dict[str, float]:
    terms = re.findall(r"[a-zA-Z0-9+#.]+", text.lower())
    counts: dict[str, int] = {}
    for term in terms:
        counts[term] = counts.get(term, 0) + 1
    return {term: 1.0 + math.log(count) for term, count in counts.items()}


def _cosine_sparse(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(weight * right.get(term, 0.0) for term, weight in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / max(1e-9, left_norm * right_norm)

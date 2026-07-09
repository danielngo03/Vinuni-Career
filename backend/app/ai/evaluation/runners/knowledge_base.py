"""Eval runner + checker for the ``knowledge_base_query`` family.

Exercises the real §6.5 citation verifier
(``app.ai.retrieval.citation_verify.verify_citations``) — pure, deterministic,
no DB/network. This is the safety net between a KB-grounded LLM answer and
the user: it strips any citation naming a document that was not actually
retrieved this turn.
"""

from __future__ import annotations

from typing import Any

from app.ai.evaluation.models import Probe
from app.ai.retrieval.citation_verify import verify_citations


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    answer = inp.get("answer", "")
    sources = inp.get("sources") or []
    result = verify_citations(answer, sources)
    data = {
        "clean_answer": result.clean_answer,
        "hallucination_risk": result.hallucination_risk,
        "cited_count": result.cited_count,
        "grounded_count": result.grounded_count,
        "ungrounded_count": result.ungrounded_count,
        "citation_grounded_rate": result.citation_grounded_rate,
    }
    return Probe(kind="kb", blob=result.clean_answer.lower(), data=data)


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``knowledge_base_query`` (§6.5 citation) probes."""
    d = probe.data
    if key == "hallucination_risk":
        got: Any = bool(d.get("hallucination_risk"))
        return None if got == bool(exp) else f"hallucination_risk expected {exp}, got {got}"
    if key == "cited_count":
        got = d.get("cited_count")
        return None if got == exp else f"cited_count expected {exp!r}, got {got!r}"
    if key == "grounded_count":
        got = d.get("grounded_count")
        return None if got == exp else f"grounded_count expected {exp!r}, got {got!r}"
    if key == "ungrounded_count":
        got = d.get("ungrounded_count")
        return None if got == exp else f"ungrounded_count expected {exp!r}, got {got!r}"
    if key == "clean_answer_excludes":
        return (
            None if str(exp).lower() not in probe.blob else (f"clean_answer should exclude {exp!r}")
        )
    if key == "clean_answer_contains":
        return None if str(exp).lower() in probe.blob else f"clean_answer should contain {exp!r}"
    if key == "no_crash":
        return None
    return None  # unknown / informational key

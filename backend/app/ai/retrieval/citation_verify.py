"""Post-generation citation verification for RAG answers (AI_PRODUCT_SPEC.md §6.5).

After the LLM produces a knowledge-base-grounded answer, this module verifies
that every document the model claims to cite ("Theo <Doc>..." /
"According to <Doc>...") actually exists among the chunks that were really
retrieved for this turn. A citation referencing a document NOT in the
retrieved set is a **hallucination risk** — this is stripped from the answer
and flagged, so no fabricated source ever reaches the user.

Pure, deterministic, offline — no model call, no network, no DB. Safe to run
on every KB-grounded turn at zero extra cost.

Never log: raw answer text, raw chunk content, or the fabricated citation
name itself beyond a redacted count (§15 privacy rules). Callers should log
only ``cited_count``, ``grounded_count``, and ``hallucination_risk``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Matches "Theo <Document Name>" / "According to <Document Name>" up to the
# first sentence/clause delimiter. Case-insensitive; Vietnamese + English.
_CITATION_RE = re.compile(
    r"(?:Theo|According to)\s+([^\n,.;—]+?)(?=\s*[—-]|\s*:|,|\.|\n|$)",
    re.IGNORECASE,
)

# Safe, generic replacement text used when a cited document cannot be
# verified against the retrieved source set. Never echoes the fabricated name.
_UNGROUNDED_REPLACEMENT = "tài liệu được cung cấp"


def _normalize(name: str) -> str:
    """Lowercase, collapse whitespace, and strip quotes/punctuation for comparison."""
    cleaned = name.strip().strip("\"'“”‘’.,;:—-")
    return re.sub(r"\s+", " ", cleaned).lower()


@dataclass(slots=True)
class CitationCheckResult:
    """Outcome of verifying every citation in an answer against real sources."""

    clean_answer: str
    hallucination_risk: bool
    cited_count: int
    grounded_count: int
    ungrounded_count: int = 0
    # Informational only — never logged verbatim (§15); useful for unit tests
    # and the eval harness, which run fully offline with synthetic data.
    ungrounded_names: list[str] = field(default_factory=list)

    @property
    def citation_grounded_rate(self) -> float | None:
        """§10.4 metric: grounded citations / total citations. ``None`` if no citations."""
        if self.cited_count == 0:
            return None
        return self.grounded_count / self.cited_count


def verify_citations(answer: str, sources: list[str]) -> CitationCheckResult:
    """Verify every ``Theo <Doc>`` / ``According to <Doc>`` citation in ``answer``.

    Args:
        answer: The LLM's final natural-language reply for this turn.
        sources: Document titles/names that were ACTUALLY retrieved this turn
            (e.g. ``[chunk["document_title"] for chunk in kb_result["chunks"]]``).
            An empty list means "no KB context was retrieved" — any citation
            found in that case is automatically ungrounded.

    Returns:
        A :class:`CitationCheckResult`. ``clean_answer`` has every ungrounded
        citation's document name replaced with a safe generic phrase; grounded
        citations are left untouched. If there are no citation markers at all,
        ``clean_answer == answer`` and ``hallucination_risk`` is ``False``.
    """
    if not answer:
        return CitationCheckResult(
            clean_answer=answer, hallucination_risk=False, cited_count=0, grounded_count=0
        )

    matches = list(_CITATION_RE.finditer(answer))
    if not matches:
        return CitationCheckResult(
            clean_answer=answer, hallucination_risk=False, cited_count=0, grounded_count=0
        )

    normalized_sources = {_normalize(s) for s in sources if s}

    grounded_count = 0
    ungrounded_names: list[str] = []
    clean_answer = answer

    # Process matches in reverse span order so earlier string offsets stay
    # valid while we splice the (possibly shorter) replacement text in.
    for m in reversed(matches):
        raw_name = m.group(1).strip()
        norm_name = _normalize(raw_name)
        is_grounded = bool(norm_name) and any(
            norm_name == src or norm_name in src or src in norm_name for src in normalized_sources
        )
        if is_grounded:
            grounded_count += 1
            continue

        ungrounded_names.append(raw_name)
        start = m.start(0)
        end = m.end(1)  # keep the trailing delimiter (":", "—", ".", etc.) intact
        clean_answer = clean_answer[:start] + _UNGROUNDED_REPLACEMENT + clean_answer[end:]

    cited_count = len(matches)
    ungrounded_count = len(ungrounded_names)
    return CitationCheckResult(
        clean_answer=clean_answer,
        hallucination_risk=ungrounded_count > 0,
        cited_count=cited_count,
        grounded_count=grounded_count,
        ungrounded_count=ungrounded_count,
        ungrounded_names=ungrounded_names,
    )


def kb_source_titles(chunks: list[dict]) -> list[str]:
    """Extract the retrieved document titles from a ``search_chunks``/tool result.

    Shared helper so every caller (chat tool loop, eval harness) builds the
    ``sources`` list the same way instead of re-deriving the chunk shape.
    """
    titles: list[str] = []
    for chunk in chunks or []:
        title = (chunk or {}).get("document_title")
        if title and title not in titles:
            titles.append(title)
    return titles

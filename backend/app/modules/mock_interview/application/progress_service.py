"""Student progress across mock interviews (no scoring — themes over time).

Since the product deliberately has no score, "progress" is expressed as the
RECURRING themes the student keeps being coached on (gaps to work on) and the
strengths that keep showing up, plus the focus mix they've practiced. Aggregated
in Python over the student's own completed sessions (small N, owner-scoped).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mock_interview.api import presenters
from app.modules.mock_interview.infrastructure import repository as repo
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import Principal

# Known focus buckets. Anything else (legacy/missing grounding) folds to the
# neutral "mixed" default so an internal "unknown" enum never reaches the UI.
_KNOWN_FOCUS = frozenset({"technical", "behavioral", "mixed"})

# Generic connectors dropped from the theme signature so paraphrases of the same
# coaching point cluster together (en + vi). Deliberately small: over-stripping
# would merge distinct themes.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
        "your", "you", "this", "that", "how", "when", "what", "more", "be", "is",
        "are", "as", "at", "by", "it", "its", "their", "them", "using", "use",
        "about", "into", "from", "not", "can", "should", "would", "could", "need",
        "needs", "được", "một", "các", "những", "cho", "với", "trong", "khi",
        "về", "để", "là", "có", "cần", "hơn", "cách", "theo", "như", "này", "đó",
        "hãy", "bằng", "và", "của", "bạn",
    }
)


def _require_student(principal: Principal) -> None:
    if principal.user_id is None:
        raise AuthRequiredError()
    if not principal.is_superadmin and principal.persona != "student":
        raise PermissionDeniedError(details={"reason": "student_only"})


def _canonical_key(text: object) -> str:
    """Cluster key for a coaching theme: its sorted set of significant keywords.

    Exact-string matching almost never fires "recurring" because the coach
    phrases the same gap differently every session. Reducing a theme to its
    significant-keyword signature makes paraphrases within a language cluster
    (e.g. "Use the STAR method" and "Structure answers with STAR" → "star").
    Cross-language equivalents still count separately (that needs translation).
    """

    tokens = re.findall(r"\w+", str(text).lower(), re.UNICODE)
    signature = sorted({w for w in tokens if len(w) >= 3 and w not in _STOPWORDS})
    key = " ".join(signature[:8])
    return key or " ".join(tokens)[:80]


def _themes(
    counter: Counter[str], repr_map: dict[str, str], *, top: int
) -> list[dict[str, Any]]:
    return [
        {"text": repr_map[key], "count": count, "recurring": count >= 2}
        for key, count in counter.most_common(top)
    ]


async def build_progress(
    session: AsyncSession, *, principal: Principal
) -> dict[str, Any]:
    _require_student(principal)
    assert principal.user_id is not None
    rows = await repo.completed_with_reports(
        session, user_id=principal.user_id, limit=60
    )

    gap_counter: Counter[str] = Counter()
    gap_repr: dict[str, str] = {}
    strength_counter: Counter[str] = Counter()
    strength_repr: dict[str, str] = {}
    focus_counter: Counter[str] = Counter()

    for row in rows:
        report = row.report_json or {}
        for gap in report.get("gaps_to_work_on") or []:
            key = _canonical_key(gap)
            if key:
                gap_counter[key] += 1
                gap_repr.setdefault(key, str(gap)[:160])
        for strength in report.get("strengths") or []:
            key = _canonical_key(strength)
            if key:
                strength_counter[key] += 1
                strength_repr.setdefault(key, str(strength)[:160])
        grounding = row.grounding_json if isinstance(row.grounding_json, dict) else {}
        focus = str(grounding.get("focus") or "").strip().lower()
        focus_counter[focus if focus in _KNOWN_FOCUS else "mixed"] += 1

    return {
        "completed": len(rows),
        "recurring_gaps": _themes(gap_counter, gap_repr, top=6),
        "top_strengths": _themes(strength_counter, strength_repr, top=6),
        "by_focus": dict(focus_counter),
        "recent": [presenters.session_summary(r) for r in rows[:5]],
    }

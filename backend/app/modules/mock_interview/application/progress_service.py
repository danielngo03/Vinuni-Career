"""Student progress across mock interviews (no scoring — themes over time).

Since the product deliberately has no score, "progress" is expressed as the
RECURRING themes the student keeps being coached on (gaps to work on) and the
strengths that keep showing up, plus the focus mix they've practiced. Aggregated
in Python over the student's own completed sessions (small N, owner-scoped).
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mock_interview.api import presenters
from app.modules.mock_interview.infrastructure import repository as repo
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import Principal


def _require_student(principal: Principal) -> None:
    if principal.user_id is None:
        raise AuthRequiredError()
    if not principal.is_superadmin and principal.persona != "student":
        raise PermissionDeniedError(details={"reason": "student_only"})


def _norm(text: object) -> str:
    return " ".join(str(text).lower().split())[:80]


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
            key = _norm(gap)
            if key:
                gap_counter[key] += 1
                gap_repr.setdefault(key, str(gap)[:160])
        for strength in report.get("strengths") or []:
            key = _norm(strength)
            if key:
                strength_counter[key] += 1
                strength_repr.setdefault(key, str(strength)[:160])
        grounding = row.grounding_json if isinstance(row.grounding_json, dict) else {}
        focus_counter[str(grounding.get("focus") or "unknown")] += 1

    return {
        "completed": len(rows),
        "recurring_gaps": _themes(gap_counter, gap_repr, top=6),
        "top_strengths": _themes(strength_counter, strength_repr, top=6),
        "by_focus": dict(focus_counter),
        "recent": [presenters.session_summary(r) for r in rows[:5]],
    }

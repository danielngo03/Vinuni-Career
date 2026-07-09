"""Inbound rating facade (ADR-0013): the ONLY seam `organization` uses to read
company review aggregates for the public profile/directory.

Reads `proj_company_rating` (the recompute-on-event read model) — never a live
JOIN over reviews on the guest surface. `organization` calls
`ratings_for(org_ids)` and embeds the returned block; it never imports the
`reviews` ORM. Orgs with no published reviews are simply absent from the result
(caller renders a "no reviews yet" empty state, never a fabricated score).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reviews.domain.models import ProjCompanyRating


def _num(value: float | None) -> float | None:
    return float(value) if value is not None else None


def _block(row: ProjCompanyRating) -> dict:
    return {
        "review_count": int(row.review_count),
        "overall_avg": _num(row.overall_avg),
        "overall_raw_avg": _num(row.overall_raw_avg),
        "categories": {
            "work_life_balance": _num(row.work_life_balance_avg),
            "culture_values": _num(row.culture_values_avg),
            "compensation": _num(row.compensation_avg),
            "career_growth": _num(row.career_growth_avg),
            "interview_experience": _num(row.interview_experience_avg),
        },
        "distribution": dict(row.distribution or {}),
    }


async def ratings_for(session: AsyncSession, org_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Batch-resolve ``{org_id: rating_block}`` for orgs that have a projection row."""

    ids = {i for i in org_ids if i is not None}
    if not ids:
        return {}
    rows = (
        (await session.execute(select(ProjCompanyRating).where(ProjCompanyRating.org_id.in_(ids))))
        .scalars()
        .all()
    )
    return {row.org_id: _block(row) for row in rows if row.review_count > 0}

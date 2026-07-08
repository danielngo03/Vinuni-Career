"""Company-rating projection recompute (ADR-0013 read model).

`recompute(session, org_id)` rebuilds the single `proj_company_rating` row for an
org from its PUBLISHED *and* FLAGGED (reported-but-not-removed), non-deleted
reviews. Full-recompute (not incremental) so it is idempotent and self-correcting;
called synchronously by the review/moderation services inside the same transaction
whenever an org's published set changes (publish / remove / restore / author-delete
/ flag-on-report). `n=0` collapses the row to NULL averages so the public surface
shows a real empty state, never the 3.0 prior as a score.

ADR-0013 rule: a flagged review stays publicly visible and counted in the aggregate.
Report spam cannot suppress a legitimate review from the rating calculation.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reviews.domain import entities
from app.modules.reviews.domain.models import (
    CompanyReview,
    ProjCompanyRating,
    ReviewRating,
)


def _avg_col(values: list[int | None]) -> float | None:
    return entities.simple_average(values)


async def recompute(session: AsyncSession, org_id: uuid.UUID) -> dict:
    """Rebuild the org's rating projection row from published+flagged reviews. Flush-only."""

    # Both PUBLISHED and FLAGGED (reported-but-not-removed) reviews count in the
    # aggregate. Flagging moves a review from published→flagged for moderator
    # attention but does NOT remove it from the public rating (ADR-0013).
    rows = (
        await session.execute(
            select(ReviewRating)
            .join(CompanyReview, CompanyReview.id == ReviewRating.review_id)
            .where(
                CompanyReview.org_id == org_id,
                CompanyReview.status.in_((
                    entities.STATUS_PUBLISHED,
                    entities.STATUS_FLAGGED,
                )),
                CompanyReview.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    overalls = [r.overall for r in rows]
    payload = {
        "org_id": org_id,
        "review_count": len(rows),
        "overall_avg": entities.bayesian_average(overalls),
        "overall_raw_avg": entities.simple_average(overalls),
        "work_life_balance_avg": _avg_col([r.work_life_balance for r in rows]),
        "culture_values_avg": _avg_col([r.culture_values for r in rows]),
        "compensation_avg": _avg_col([r.compensation for r in rows]),
        "career_growth_avg": _avg_col([r.career_growth for r in rows]),
        "interview_experience_avg": _avg_col(
            [r.interview_experience for r in rows]
        ),
        "distribution": entities.distribution(overalls),
    }

    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    stmt = insert(ProjCompanyRating).values(**payload)
    update_cols = {k: stmt.excluded[k] for k in payload if k != "org_id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=[ProjCompanyRating.org_id], set_=update_cols
    )
    await session.execute(stmt)
    await session.flush()
    return payload

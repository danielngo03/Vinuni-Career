"""Application-access facade — "does this student have a live application here?".

A tiny read-model seam other modules (e.g. ``knowledge_base``) use to answer
whether a student's application to an org / job is still ACTIVE, without reaching
into the recruitment ``Application`` ORM directly (module-boundary rule). "Active"
means any status that is not ``rejected`` / ``withdrawn`` — matching the
applicant-facing KB access rule ("access revoked on REJECTED/WITHDRAWN").

Replaces the previous knowledge_base raw SQL that queried a non-existent
``job_applications`` table (the real table is ``applications`` with a direct
``org_id`` column), so the applicant-facing path never actually granted access.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.recruitment.domain import lifecycle
from app.modules.recruitment.domain.models import Application

# Access is revoked once an application reaches a terminal negative state.
_INACTIVE_STATUSES = frozenset({lifecycle.REJECTED, lifecycle.WITHDRAWN})


async def has_active_application_to_org(
    session: AsyncSession, *, user_id: uuid.UUID | None, org_id: uuid.UUID | None
) -> bool:
    """True if the user has at least one non-rejected/withdrawn application to ``org_id``."""
    if user_id is None or org_id is None:
        return False
    row = (
        await session.execute(
            select(Application.id).where(
                Application.applicant_id == user_id,
                Application.org_id == org_id,
                Application.status.notin_(_INACTIVE_STATUSES),
                Application.deleted_at.is_(None),
            ).limit(1)
        )
    ).first()
    return row is not None


async def has_active_application_to_job(
    session: AsyncSession, *, user_id: uuid.UUID | None, job_id: uuid.UUID | None
) -> bool:
    """True if the user has at least one non-rejected/withdrawn application to ``job_id``."""
    if user_id is None or job_id is None:
        return False
    row = (
        await session.execute(
            select(Application.id).where(
                Application.applicant_id == user_id,
                Application.job_id == job_id,
                Application.status.notin_(_INACTIVE_STATUSES),
                Application.deleted_at.is_(None),
            ).limit(1)
        )
    ).first()
    return row is not None

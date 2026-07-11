"""Review-eligibility facade (ADR-0013): may a student review an employer?

`reviews` asks this seam — never reading the `applications` ORM — whether a
student has interacted with an org strongly enough to review it, and returns the
strongest interaction class:

- ``system_verified_offer`` — an application to that org reached ``hired`` (the
  accepted-offer terminal state, the strongest proof);
- ``system_verified_interview`` — an application reached ``under_review`` (the
  partner actively engaged the candidate), the interaction proxy for slice-1
  (a tighter interview-stage check is a later refinement);
- ``None`` — no qualifying interaction → the student cannot review (caller 403s).

Self-declared / partner-verified classes are out of slice-1 (verified-only).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.recruitment.domain import lifecycle
from app.modules.recruitment.domain.models import Application

ELIG_OFFER = "system_verified_offer"
ELIG_INTERVIEW = "system_verified_interview"


async def eligibility_for(
    session: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID
) -> tuple[str, uuid.UUID] | None:
    """Strongest ``(eligibility_type, application_id)`` for this student↔org, or None."""

    rows = (
        await session.execute(
            select(Application.id, Application.status).where(
                Application.applicant_id == user_id,
                Application.org_id == org_id,
            )
        )
    ).all()
    if not rows:
        return None

    offer_app = next((r.id for r in rows if r.status == lifecycle.HIRED), None)
    if offer_app is not None:
        return ELIG_OFFER, offer_app
    interview_app = next((r.id for r in rows if r.status == lifecycle.UNDER_REVIEW), None)
    if interview_app is not None:
        return ELIG_INTERVIEW, interview_app
    return None

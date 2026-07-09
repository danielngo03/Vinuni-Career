"""Read-only projection of the recruitment reveal state the talent-pool DETAIL
masking depends on.

The passive talent-pool profile detail (``GET /students/{id}/profile``) gives an
external partner recruiter the SAME blind-screening mask as the talent-pool LIST:
the candidate's real name + identifying avatar are withheld behind the opaque
``UV-xxxx`` handle until the candidate has ENGAGED — i.e. until this partner org
holds an ACCEPTED identity reveal for this candidate through the recruitment
reveal handshake (``docs/PARTNER_RBAC_ANALYTICS_SPEC.md`` — candidate identity
protection).

It must read that fact WITHOUT importing ``recruitment``'s ORM/services (module
boundary), so it queries the ``applications`` table as a lightweight read model
(SQLAlchemy Core ``table()`` with only the columns it needs), mirroring the
messaging module's ``recruitment_relationship`` read-model pattern (ADR-0012
§3/§8). The shape is decoupled from how recruitment stores its rows.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, column, func, select, table
from sqlalchemy.ext.asyncio import AsyncSession

# Lightweight read-model view of the recruitment-owned table — NOT the ORM model,
# so student_profiles stays decoupled from recruitment's implementation.
_applications = table(
    "applications",
    column("org_id"),
    column("applicant_id"),
    column("reveal_approved_at"),
    column("deleted_at"),
)


async def has_revealed_candidate(
    session: AsyncSession, *, org_id: uuid.UUID, applicant_user_id: uuid.UUID
) -> bool:
    """True if this partner org holds an ACCEPTED identity reveal for the candidate.

    ``reveal_approved_at IS NOT NULL`` on any live application binding this partner
    org to this candidate means the reveal handshake was accepted — the mask on the
    passive profile detail may be lifted (subject to the caller's additional
    ``candidate_identity:view_revealed_identity`` capability check).
    """

    stmt = (
        select(func.count())
        .select_from(_applications)
        .where(
            and_(
                _applications.c.org_id == org_id,
                _applications.c.applicant_id == applicant_user_id,
                _applications.c.reveal_approved_at.is_not(None),
                _applications.c.deleted_at.is_(None),
            )
        )
    )
    return bool((await session.execute(stmt)).scalar_one())

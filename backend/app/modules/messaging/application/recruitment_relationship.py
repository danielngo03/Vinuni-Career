"""Read-only projection of the recruitment relationship messaging depends on.

ADR-0012 §3/§8: messaging binds every partner↔student thread to an ``applications``
row, and masks the student until the reveal handshake completes. It must read those
facts WITHOUT a cross-module implementation import — so this module queries the
``applications`` table as a lightweight read model (SQLAlchemy Core ``table()`` with
only the columns messaging needs), never importing ``recruitment``'s ORM class or
services. The shape is a small immutable DTO, decoupled from how recruitment stores
its rows.

Only the relationship facts the permission matrix + masking need are read:
``org_id`` (tenant + partner ownership), ``applicant_id`` (the bound student),
``status`` (active vs. inactive taper), ``is_anonymous`` + ``reveal_approved_at``
(the masking decision).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, column, func, select, table
from sqlalchemy.ext.asyncio import AsyncSession

# Lightweight read-model view of the recruitment-owned table. NOT the ORM model —
# messaging stays decoupled from recruitment's implementation.
_applications = table(
    "applications",
    column("id"),
    column("org_id"),
    column("applicant_id"),
    column("status"),
    column("is_anonymous"),
    column("reveal_approved_at"),
    column("deleted_at"),
)


@dataclass(frozen=True, slots=True)
class ApplicationRelationship:
    application_id: uuid.UUID
    org_id: uuid.UUID
    applicant_id: uuid.UUID
    status: str
    is_anonymous: bool
    reveal_approved_at: datetime | None

    @property
    def is_revealed(self) -> bool:
        return self.reveal_approved_at is not None


def _coerce_uuid(value: object) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _row_to_relationship(row) -> ApplicationRelationship:
    return ApplicationRelationship(
        application_id=_coerce_uuid(row.id),
        org_id=_coerce_uuid(row.org_id),
        applicant_id=_coerce_uuid(row.applicant_id),
        status=str(row.status),
        is_anonymous=bool(row.is_anonymous),
        reveal_approved_at=row.reveal_approved_at,
    )


async def load_relationship(
    session: AsyncSession, *, application_id: uuid.UUID
) -> ApplicationRelationship | None:
    """Load the bound application's relationship facts (or ``None`` if missing/purged)."""

    stmt = select(
        _applications.c.id,
        _applications.c.org_id,
        _applications.c.applicant_id,
        _applications.c.status,
        _applications.c.is_anonymous,
        _applications.c.reveal_approved_at,
    ).where(
        and_(
            _applications.c.id == application_id,
            _applications.c.deleted_at.is_(None),
        )
    )
    row = (await session.execute(stmt)).first()
    return _row_to_relationship(row) if row is not None else None


async def relationship_exists(
    session: AsyncSession, *, org_id: uuid.UUID, applicant_id: uuid.UUID
) -> bool:
    """True if any live application binds this partner org to this applicant."""

    stmt = (
        select(func.count())
        .select_from(_applications)
        .where(
            and_(
                _applications.c.org_id == org_id,
                _applications.c.applicant_id == applicant_id,
                _applications.c.deleted_at.is_(None),
            )
        )
    )
    return bool((await session.execute(stmt)).scalar_one())

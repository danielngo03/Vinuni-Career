"""Internal org lookup facade for cross-module surfaces that key off a public slug.

`reviews` resolves a company profile slug to an org id through this seam (reusing
the same listable-visibility predicate the public company directory uses) instead
of importing the `Organization` ORM. Returns only the id — no status/logo_path/
contact fields can leak. A non-listable (pending/suspended/university) org returns
``None`` → the caller maps to ``404`` consistently with the public profile.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.domain.models import Organization

_PARTNER = "partner"
_ACTIVE = "active"


async def listable_id_for_slug(session: AsyncSession, *, slug: str) -> uuid.UUID | None:
    """Org id for a publicly listable partner slug, else ``None``."""

    return (
        await session.execute(
            select(Organization.id).where(
                Organization.slug == slug,
                Organization.org_type == _PARTNER,
                Organization.status == _ACTIVE,
                Organization.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

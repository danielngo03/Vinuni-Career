"""Resolve the organization a caller is allowed to *manage*.

This is the minimal cross-org shim for the university control plane (P2/WS2.3).
The org RBAC model is unchanged: for an ordinary org actor the managed org is
still, exactly, ``principal.org_id`` — the optional ``org_id`` argument is
IGNORED for non-superadmins so staff can never target another tenant. Only a
platform **superadmin** (``org_id is None``) may resolve a different org:

- an explicit ``org_id`` (validated to exist and not be soft-deleted), or
- the single ``org_type="university"`` org by default (VinUni is a
  single-institution deployment, memory ``project-context``).

Every management/read service resolves through here before enforcing RBAC +
audit, so a pure superadmin can build & govern the university org's people,
roles, and departments without weakening tenant isolation for anyone else.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.domain.models import Organization
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal

_UNIVERSITY = "university"


async def resolve_managed_org(
    session: AsyncSession,
    principal: Principal,
    *,
    org_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Return the org id ``principal`` may manage.

    Non-superadmin: always ``principal.org_id`` (``org_id`` ignored); raises
    :class:`ResourceNotFoundError` (404) when the principal has no org — today's
    behavior, byte-for-byte.

    Superadmin: the explicit ``org_id`` when supplied (404 if it does not exist
    or is soft-deleted), else the single university org (404 if none exists).
    """

    if not principal.is_superadmin:
        # Tenant isolation is unchanged for staff: their own org, or 404.
        if principal.org_id is None:
            raise ResourceNotFoundError()
        return principal.org_id

    if org_id is not None:
        exists = (
            await session.execute(
                select(Organization.id).where(
                    Organization.id == org_id,
                    Organization.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            raise ResourceNotFoundError()
        return exists

    resolved = (
        await session.execute(
            select(Organization.id)
            .where(
                Organization.org_type == _UNIVERSITY,
                Organization.deleted_at.is_(None),
            )
            .order_by(Organization.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if resolved is None:
        raise ResourceNotFoundError()
    return resolved

"""Cross-module read/write facade for partner registration requests.

The employer self-registration wizard lives in the ``onboarding`` module, but the
``PartnerRegistrationRequest`` entity is owned by the ``organization`` domain. This
facade lets ``onboarding`` create and read those requests through the organization
application layer instead of importing ``organization.domain`` directly, keeping
the module boundary clean (``docs/ARCHITECTURE.md`` §8; enforced by
``tests/integration/test_module_boundaries.py``).

Behaviour-preserving: these are the exact queries/construction the onboarding
service used inline before — just relocated into the owning module.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.domain.models import PartnerRegistrationRequest


async def get_by_user(
    session: AsyncSession, user_id: uuid.UUID
) -> PartnerRegistrationRequest | None:
    """Return the registration request submitted by ``user_id`` (or ``None``)."""

    return (
        await session.execute(
            select(PartnerRegistrationRequest).where(
                PartnerRegistrationRequest.submitted_by_user_id == user_id
            )
        )
    ).scalar_one_or_none()


async def get_by_id(
    session: AsyncSession, request_id: uuid.UUID
) -> PartnerRegistrationRequest | None:
    """Return the registration request with ``request_id`` (or ``None``)."""

    return (
        await session.execute(
            select(PartnerRegistrationRequest).where(PartnerRegistrationRequest.id == request_id)
        )
    ).scalar_one_or_none()


def create(
    session: AsyncSession,
    *,
    company_name: str,
    industry: str | None,
    company_size: str | None,
    contact_name: str,
    contact_email: str,
    contact_title: str | None,
    description: str | None,
    submitted_by_user_id: uuid.UUID,
) -> PartnerRegistrationRequest:
    """Build + stage a new registration request. The caller flushes/commits."""

    req = PartnerRegistrationRequest(
        company_name=company_name,
        industry=industry,
        company_size=company_size,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_title=contact_title,
        description=description,
        submitted_by_user_id=submitted_by_user_id,
    )
    session.add(req)
    return req


__all__ = ["get_by_user", "get_by_id", "create"]

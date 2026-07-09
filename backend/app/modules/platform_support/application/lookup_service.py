"""Support-console account/org lookup (``GET /platform-support/lookup``).

Wraps ``admin_users_service.list_platform_users`` (users) +
``org_reporting_facade.search_orgs`` (orgs). No new tables; never exposes raw
PII beyond what those existing admin-safe facades already return.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.application import org_reporting_facade
from app.modules.platform_support.application._shared import require_support
from app.modules.users.application import admin_users_service
from app.shared.exceptions import ValidationFailedError
from app.shared.permissions import Principal

_VALID_TYPES = frozenset({"user", "organization"})


async def lookup(
    session: AsyncSession,
    *,
    principal: Principal,
    q: str | None,
    type_: str,
    page: int = 1,
    page_size: int = 30,
) -> dict:
    await require_support(session, principal, "read")
    if type_ not in _VALID_TYPES:
        raise ValidationFailedError(details={"field": "type"})

    if type_ == "user":
        return await admin_users_service.list_platform_users(
            session, principal=principal, q=q, page=page, page_size=page_size
        )
    return await org_reporting_facade.search_orgs(session, q=q, page=page, page_size=page_size)

"""Shared RBAC gate + audit helpers for the ``platform_support`` module.

No new ORM tables here (ADR-0014 §1). Every gate additionally requires
``org_reporting_facade.is_university_org`` — mirrors
``review_queue_service._require_university`` / ``admin_users_service.
_require_account_governor`` — so a misconfigured partner role can never hold
``support:*`` even if granted by mistake.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import Principal, permission_checker


def now() -> datetime:
    return datetime.now(tz=UTC)


def audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def require_support(
    session: AsyncSession, principal: Principal, action: str
) -> None:
    """``support:{action}`` + university-org gate (superadmin bypasses)."""

    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.is_superadmin:
        return
    if not permission_checker.can(principal, "support", action):
        raise PermissionDeniedError()
    if not await org_reporting_facade.is_university_org(session, principal.org_id):
        raise PermissionDeniedError(details={"reason": "university_only"})

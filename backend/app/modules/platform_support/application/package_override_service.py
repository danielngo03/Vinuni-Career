"""Support-console package override (``POST /platform-support/users/{id}/package-override``).

Thin wrapper delegating to the existing ``billing`` package-assignment
internals (:func:`billing.moderation_service.admin_override_grant`) — the
support call site is audited HERE in addition to whatever audit ``billing``
already writes for the grant itself.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.billing.application import moderation_service as billing_moderation
from app.modules.platform_support.application._shared import audit_ctx, require_support
from app.shared.audit import write_audit
from app.shared.exceptions import ValidationFailedError
from app.shared.permissions import Principal


async def override_package(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    reason: str,
) -> dict:
    await require_support(session, principal, "act")
    if not reason or not reason.strip():
        raise ValidationFailedError(details={"field": "reason"})

    result = await billing_moderation.admin_override_grant(
        session,
        principal=principal,
        ctx=ctx,
        user_id=user_id,
        plan_id=plan_id,
        reason=reason,
    )

    await write_audit(
        session,
        action="support.package_overridden",
        resource_type="support_billing",
        resource_id=user_id,
        context=audit_ctx(principal, ctx),
        after={"user_id": str(user_id), "plan_id": str(plan_id), "reason": reason.strip()[:200]},
    )
    await session.commit()
    return result

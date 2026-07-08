"""Support-console PII reveal (``POST /platform-support/reveal/{type}/{id}``).

Masked PII (raw CV text, contact info) is masked by default in every support
view; this endpoint's REVEAL ITSELF is the audited action — the audit row
NEVER contains the revealed value, only ``{"target_type", "target_id",
"reason"}``. V1 scope is intentionally small (``user_contact`` only, resolved
through the existing ``users`` facade); other ``resource_type`` values are
documented-not-built and return ``404`` rather than silently succeeding.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.platform_support.application._shared import audit_ctx, require_support
from app.modules.users.application import user_service
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal

_SUPPORTED_RESOURCE_TYPES = frozenset({"user_contact"})


async def reveal(
    session: AsyncSession,
    *,
    principal: Principal,
    resource_type: str,
    resource_id: uuid.UUID,
    reason: str,
    ctx: RequestContext,
) -> dict:
    await require_support(session, principal, "act")
    if not reason or not reason.strip():
        raise ValidationFailedError(details={"field": "reason"})
    if resource_type not in _SUPPORTED_RESOURCE_TYPES:
        raise ResourceNotFoundError(details={"reason": "unsupported_resource_type"})

    if resource_type == "user_contact":
        user = await user_service.get_by_id(session, resource_id)
        if user is None:
            raise ResourceNotFoundError()
        revealed = {"email": user.email, "full_name": user.full_name}
    else:  # pragma: no cover - unreachable given the allowlist above
        raise ResourceNotFoundError()

    # The audited action is the reveal EVENT, never the revealed value.
    await write_audit(
        session,
        action="support.pii_revealed",
        resource_type="support_reveal",
        resource_id=resource_id,
        context=audit_ctx(principal, ctx),
        after={
            "target_type": resource_type,
            "target_id": str(resource_id),
            "reason": reason.strip()[:500],
        },
    )
    await session.commit()
    return revealed

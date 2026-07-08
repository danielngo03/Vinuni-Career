"""Support-console outbox health read + requeue (ADR-0014 §1, API_CONTRACTS).

Reads compose ``notification_outbox`` (the real per-row dispatch queue, not
the generic ``OutboxEvent`` domain-event outbox — a different table).
Requeue is only legal on ``status="dead"`` rows; the caller gets a clean
``409 not_dead_lettered`` otherwise via :class:`ConflictError`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import dispatch_service
from app.modules.platform_support.application._shared import audit_ctx, require_support
from app.shared.audit import write_audit
from app.shared.exceptions import ConflictError
from app.shared.permissions import Principal


async def get_health(session: AsyncSession, *, principal: Principal) -> dict:
    await require_support(session, principal, "read")
    counts = await dispatch_service.status_counts(session)
    now = datetime.now(tz=UTC)
    return {
        **counts,
        "oldest_pending_age_seconds": await dispatch_service.oldest_pending_age_seconds(
            session, now=now
        ),
        "retry_scheduled": await dispatch_service.retry_scheduled_count(session, now=now),
    }


async def requeue(
    session: AsyncSession,
    *,
    principal: Principal,
    outbox_id: uuid.UUID,
    ctx: RequestContext,
) -> dict:
    await require_support(session, principal, "act")
    try:
        row = await dispatch_service.requeue_dead_letter(session, outbox_id=outbox_id)
    except ValueError as exc:
        raise ConflictError(details={"reason": "not_dead_lettered"}) from exc

    await write_audit(
        session,
        action="support.outbox_requeued",
        resource_type="support_notification_outbox",
        resource_id=row.id,
        context=audit_ctx(principal, ctx),
        after={"outbox_id": str(row.id), "template_key": row.template_key},
    )
    await session.commit()
    return {"id": str(row.id), "status": row.status}

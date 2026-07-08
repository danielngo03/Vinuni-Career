"""Support-case queue (``human_review_queue`` rows, ``source="support_case"``).

``/platform-support/cases`` is a thin filter over
``/moderation/review-queue?source=support_case`` — no duplicate UI/table (per
API_CONTRACTS "link-out per product decision"). ``create_case`` is the
internal write path a support agent action uses to open a case (e.g. escalate
a lookup finding for follow-up); resolve/dismiss delegate to
``review_queue_service`` with the ``support_case`` source validated, and are
ALSO audited under a ``support.*`` action in addition to the existing
``moderation.review_item_*`` audit row ``review_queue_service`` already
writes.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.moderation.application import review_queue_service
from app.modules.moderation.application.review_queue_service import SOURCE_SUPPORT_CASE
from app.modules.platform_support.application._shared import audit_ctx, require_support
from app.shared.audit import write_audit
from app.shared.exceptions import ConflictError, ResourceNotFoundError
from app.shared.permissions import Principal


def _present(item: Any) -> dict:
    return {
        "id": str(item.id),
        "resource_type": item.resource_type,
        "resource_id": str(item.resource_id) if item.resource_id else None,
        "severity": item.severity,
        "status": item.status,
        "findings": item.findings_json,
        "created_at": item.created_at.isoformat(),
    }


async def list_cases(
    session: AsyncSession, *, principal: Principal, status: str | None = None, limit: int = 50
) -> list[dict]:
    await require_support(session, principal, "read")
    items = await review_queue_service.list_items_unchecked(
        session,
        status=status,
        source=SOURCE_SUPPORT_CASE,
        limit=limit,
    )
    return [_present(i) for i in items]


async def create_case(
    session: AsyncSession,
    *,
    principal: Principal,
    resource_type: str,
    resource_id: uuid.UUID | None,
    findings: dict,
    ctx: RequestContext,
) -> dict:
    await require_support(session, principal, "act")
    item = await review_queue_service.enqueue(
        session,
        source=SOURCE_SUPPORT_CASE,
        resource_type=resource_type,
        resource_id=resource_id,
        org_id=principal.org_id,
        severity="low",
        findings=findings,
    )
    assert item is not None
    return _present(item)


async def resolve_case(
    session: AsyncSession,
    *,
    principal: Principal,
    item_id: uuid.UUID,
    note: str | None,
    ctx: RequestContext,
) -> dict:
    await require_support(session, principal, "act")
    source = await review_queue_service.get_source(session, item_id)
    if source is None:
        raise ResourceNotFoundError()
    if source != SOURCE_SUPPORT_CASE:
        raise ConflictError(details={"reason": "not_a_support_case"})

    item = await review_queue_service.resolve_item(
        session,
        principal=principal,
        ctx=ctx,
        item_id=item_id,
        note=note,
        skip_permission_check=True,
    )

    await write_audit(
        session,
        action="support.case_resolved",
        resource_type="support_case",
        resource_id=item.id,
        context=audit_ctx(principal, ctx),
        after={"status": item.status},
    )
    await session.commit()
    return _present(item)

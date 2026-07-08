"""Org-scoped audit-log read (B-518/523).

Every write path across the platform funnels through ``app.shared.audit.write_audit``
and stamps ``actor_org_id``. This read model lets an org actor with the ``audit:read``
grant (or ``members:read`` as an equivalent baseline — see ``_require_audit_read``)
page through their own org's audit trail with actor/action/date filters. Tenant
isolation: only rows stamped with the caller's ``org_id`` are ever returned.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.application.org_resolution import resolve_managed_org
from app.modules.users.application import user_read_facade
from app.shared.models import AuditLog
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal, permission_checker


def _require_audit_read(principal: Principal, *, org_id: uuid.UUID) -> None:
    """``audit:read`` OR ``members:read`` (the pre-existing team-visibility grant)."""

    if permission_checker.can(principal, "audit", "read", resource_org_id=org_id):
        return
    permission_checker.require(principal, "members", "read", resource_org_id=org_id)


async def list_audit_log(
    session: AsyncSession,
    *,
    principal: Principal,
    cursor: str | None = None,
    limit: int | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    org_id: uuid.UUID | None = None,
):
    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    _require_audit_read(principal, org_id=org_id)
    page_limit = clamp_limit(limit)

    stmt = select(AuditLog).where(AuditLog.actor_org_id == org_id)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if since is not None:
        stmt = stmt.where(AuditLog.occurred_at >= since)
    if until is not None:
        stmt = stmt.where(AuditLog.occurred_at <= until)

    decoded = decode_cursor(cursor)
    if decoded is not None and "id" in decoded:
        stmt = stmt.where(AuditLog.id < int(decoded["id"]))
    stmt = stmt.order_by(AuditLog.id.desc()).limit(page_limit + 1)

    rows = list((await session.execute(stmt)).scalars().all())
    page = build_cursor_page(
        rows, limit=page_limit, cursor_builder=lambda row: {"id": str(row.id)}
    )

    actor_ids = {row.actor_id for row in page.items if row.actor_id is not None}
    contacts = await user_read_facade.get_user_contacts(session, actor_ids)
    items = [
        {
            "id": row.id,
            "actor_id": str(row.actor_id) if row.actor_id else None,
            "actor_email": (
                contacts[row.actor_id].email if row.actor_id in contacts else None
            ),
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": str(row.resource_id) if row.resource_id else None,
            "before": row.before_snapshot,
            "after": row.after_snapshot,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        }
        for row in page.items
    ]
    return items, page.next_cursor, page.limit

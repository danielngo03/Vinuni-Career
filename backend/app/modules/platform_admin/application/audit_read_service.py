"""Platform-wide audit log read service — superadmin only.

Returns rows from the shared ``AuditLog`` table with NO org-scoping filter.
This is intentionally distinct from the org-scoped ``list_audit_log`` in the
``organization`` module.  Authorization (superadmin gate) is enforced by the
caller (router dep) *and* re-checked here so the service layer cannot be
bypassed.

Privacy rules:
- ``ip_hash`` and ``user_agent_hash`` are never returned to callers.
- ``before_snapshot`` / ``after_snapshot`` are returned in the list API for
  superadmin inspection but are excluded from the CSV export (keep it flat).
- ``actor_email`` is enriched via the internal ``user_read_facade`` (no PII
  beyond what the superadmin already has access to).
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.application import user_read_facade
from app.shared.exceptions import PermissionDeniedError
from app.shared.models import AuditLog
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal

_DEFAULT_MAX_ROWS = 5000
_CSV_COLUMNS = [
    "occurred_at",
    "actor_email",
    "actor_id",
    "actor_org_id",
    "action",
    "resource_type",
    "resource_id",
]


def _require_superadmin(principal: Principal) -> None:
    if not principal.is_superadmin:
        raise PermissionDeniedError()


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


async def list_platform_audit(
    session: AsyncSession,
    *,
    principal: Principal,
    cursor: str | None = None,
    limit: int | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[list[dict], str | None, int]:
    """Return a cursor page of platform-wide audit log entries.

    No org filter — all rows across all organisations are visible to a
    superadmin.  Cursor is on ``AuditLog.id`` descending (newest first),
    matching the existing org-scoped service convention.

    Returns:
        (items, next_cursor, page_limit)
    """

    _require_superadmin(principal)
    page_limit = clamp_limit(limit)

    stmt = select(AuditLog)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
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
            "actor_org_id": str(row.actor_org_id) if row.actor_org_id else None,
            "actor_email": (
                contacts[row.actor_id].email if row.actor_id in contacts else None
            ),
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": str(row.resource_id) if row.resource_id else None,
            "before": row.before_snapshot,
            "after": row.after_snapshot,
            "occurred_at": _iso(row.occurred_at),
        }
        for row in page.items
    ]
    return items, page.next_cursor, page.limit


async def export_platform_audit_csv(
    session: AsyncSession,
    *,
    principal: Principal,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    max_rows: int = _DEFAULT_MAX_ROWS,
) -> str:
    """Return a UTF-8 CSV string of filtered audit log rows.

    Columns: occurred_at, actor_email, actor_id, actor_org_id, action,
    resource_type, resource_id.

    Excluded intentionally:
    - ``ip_hash`` / ``user_agent_hash`` — never expose hashed PII.
    - ``before_snapshot`` / ``after_snapshot`` — JSON blobs; keep CSV flat.

    Capped at ``max_rows`` (default 5 000) to keep the response synchronous
    and bound in size.
    """

    _require_superadmin(principal)

    stmt = select(AuditLog)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if since is not None:
        stmt = stmt.where(AuditLog.occurred_at >= since)
    if until is not None:
        stmt = stmt.where(AuditLog.occurred_at <= until)

    stmt = stmt.order_by(AuditLog.id.desc()).limit(max_rows)
    rows = list((await session.execute(stmt)).scalars().all())

    actor_ids = {row.actor_id for row in rows if row.actor_id is not None}
    contacts = await user_read_facade.get_user_contacts(session, actor_ids)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_CSV_COLUMNS)

    for row in rows:
        actor_email = (
            contacts[row.actor_id].email if row.actor_id and row.actor_id in contacts else ""
        )
        writer.writerow([
            _iso(row.occurred_at),
            actor_email,
            str(row.actor_id) if row.actor_id else "",
            str(row.actor_org_id) if row.actor_org_id else "",
            row.action,
            row.resource_type,
            str(row.resource_id) if row.resource_id else "",
        ])

    return buf.getvalue()

"""Audit writer — every write action records an audit entry.

The writer accepts raw IP / user-agent and hashes them before persistence; raw
values are never stored (``docs/SECURITY_PRIVACY.md``). Snapshots must contain
no raw CV text, prompts, or secrets — callers are responsible for passing
metadata-only diffs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.shared.hashing import hash_ip, hash_user_agent
from app.shared.models import AuditLog


@dataclass(slots=True)
class AuditContext:
    """Request-scoped context for an audited action."""

    actor_id: uuid.UUID | None = None
    actor_org_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    ip: str | None = None
    user_agent: str | None = None


async def write_audit(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    context: AuditContext | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog | None:
    """Write an audit log row within the caller's transaction.

    The row is added (flushed) but **not committed**: it shares the caller's
    transaction so the audit record and the business write commit atomically.
    Returns ``None`` when auditing is disabled by config.
    """

    settings = get_settings()
    if not settings.audit_log_enabled:
        return None

    ctx = context or AuditContext()
    entry = AuditLog(
        actor_id=ctx.actor_id,
        actor_org_id=ctx.actor_org_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before_snapshot=before,
        after_snapshot=after,
        ip_hash=hash_ip(ctx.ip),
        user_agent_hash=hash_user_agent(ctx.user_agent),
        session_id=ctx.session_id,
    )
    session.add(entry)
    await session.flush()
    return entry

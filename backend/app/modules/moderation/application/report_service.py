"""Content report submission (``docs/DATA_MODEL.md`` §35, ADR-0014).

V1 ``entity_type`` scope is ``company``/``job``/``message`` only — application
and ad-creative report buttons are deferred (documented, not built). A
duplicate ``(reporter_id, entity_type, entity_id)`` is an idempotent no-op
(the UNIQUE constraint is the primary anti-spam control); a service-layer
rate limit on distinct-entity report volume per reporter per window is the
secondary control.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.moderation.domain.models import (
    REPORT_ENTITY_TYPES,
    REPORT_STATUS_PENDING,
    ContentReport,
)
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AuthRequiredError,
    RateLimitedError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

# Max distinct-entity reports a single reporter may file within the window
# (defeats the "report many different entities in a burst" bypass of the
# per-entity UNIQUE constraint).
_RATE_LIMIT_WINDOW = timedelta(hours=1)
_RATE_LIMIT_MAX_REPORTS = 10


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _present(row: ContentReport) -> dict:
    return {
        "id": str(row.id),
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id),
        "reason_code": row.reason_code,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
    }


async def _check_rate_limit(session: AsyncSession, *, reporter_id: uuid.UUID) -> None:
    window_start = _now() - _RATE_LIMIT_WINDOW
    count = (
        await session.execute(
            select(func.count())
            .select_from(ContentReport)
            .where(
                ContentReport.reporter_id == reporter_id,
                ContentReport.created_at >= window_start,
            )
        )
    ).scalar_one()
    if count >= _RATE_LIMIT_MAX_REPORTS:
        raise RateLimitedError(details={"reason": "report_rate_limited"})


async def submit(
    session: AsyncSession,
    *,
    principal: Principal,
    entity_type: str,
    entity_id: uuid.UUID,
    reason_code: str,
    note: str | None,
    ctx: RequestContext,
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise AuthRequiredError()
    if entity_type not in REPORT_ENTITY_TYPES:
        raise ValidationFailedError(details={"reason": "unsupported_entity_type"})
    if not reason_code or not reason_code.strip():
        raise ValidationFailedError(details={"field": "reason_code"})

    existing = (
        await session.execute(
            select(ContentReport).where(
                ContentReport.reporter_id == principal.user_id,
                ContentReport.entity_type == entity_type,
                ContentReport.entity_id == entity_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"status": "already_reported", "report": _present(existing)}

    await _check_rate_limit(session, reporter_id=principal.user_id)

    row = ContentReport(
        entity_type=entity_type,
        entity_id=entity_id,
        reporter_id=principal.user_id,
        reporter_org_id=principal.org_id,
        reason_code=reason_code.strip()[:30],
        note=(note or "").strip()[:2000] or None,
        status=REPORT_STATUS_PENDING,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        # Race with a concurrent duplicate submit — treat as the same
        # idempotent outcome rather than surfacing a 500.
        await session.rollback()
        existing = (
            await session.execute(
                select(ContentReport).where(
                    ContentReport.reporter_id == principal.user_id,
                    ContentReport.entity_type == entity_type,
                    ContentReport.entity_id == entity_id,
                )
            )
        ).scalar_one()
        return {"status": "already_reported", "report": _present(existing)}

    await write_audit(
        session,
        action="moderation.content_report_submitted",
        resource_type="content_report",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        after={"entity_type": entity_type, "entity_id": str(entity_id)},
    )
    await session.commit()
    return {"status": "submitted", "report": _present(row)}

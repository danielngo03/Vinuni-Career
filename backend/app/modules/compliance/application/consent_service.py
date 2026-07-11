"""Student consent read/write (``docs/DATA_MODEL.md`` §35, ADR-0014).

Two fixed consent types only (:data:`CONSENT_TYPES`), self-service — a caller
may only read/write its own ``user_id`` row. ``consents`` is current-state
only; the audit trail (``compliance.consent_updated``) is the history.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.compliance.domain.models import CONSENT_TYPES, Consent
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import AuthRequiredError, ValidationFailedError
from app.shared.permissions import Principal


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _present(row: Consent | None) -> dict:
    if row is None:
        return {"granted": False, "granted_at": None, "revoked_at": None}
    return {
        "granted": row.granted,
        "granted_at": row.granted_at.isoformat() if row.granted_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }


async def get_mine(session: AsyncSession, *, principal: Principal) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise AuthRequiredError()
    rows = list(
        (await session.execute(select(Consent).where(Consent.user_id == principal.user_id)))
        .scalars()
        .all()
    )
    by_type = {r.consent_type: r for r in rows}
    return {ctype: _present(by_type.get(ctype)) for ctype in sorted(CONSENT_TYPES)}


async def set_mine(
    session: AsyncSession,
    *,
    principal: Principal,
    consent_type: str,
    granted: bool,
    ctx: RequestContext,
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise AuthRequiredError()
    if consent_type not in CONSENT_TYPES:
        raise ValidationFailedError(details={"field": "consent_type"})

    row = (
        await session.execute(
            select(Consent).where(
                Consent.user_id == principal.user_id,
                Consent.consent_type == consent_type,
            )
        )
    ).scalar_one_or_none()

    before = {"granted": row.granted if row is not None else False}
    now = _now()
    if row is None:
        row = Consent(user_id=principal.user_id, consent_type=consent_type, granted=False)
        session.add(row)

    row.granted = granted
    if granted:
        row.granted_at = now
        row.revoked_at = None
    else:
        row.revoked_at = now
    await session.flush()

    await write_audit(
        session,
        action="compliance.consent_updated",
        resource_type="consent",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after={"granted": granted, "consent_type": consent_type},
    )
    await session.commit()
    return _present(row)

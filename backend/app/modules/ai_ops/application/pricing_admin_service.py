"""Audited CRUD for the ``ai_model_price`` table (superadmin only).

Every write action — create and update — records an audit log row within the
same transaction so the price change and the audit are atomic.  There are no
secrets in this table, so full before/after snapshots are safe to persist.

RBAC is enforced in the router via ``require_superadmin``; this service trusts
that the caller is already authorised and concentrates on the business logic.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.observability.models import AiModelPrice
from app.modules.auth.application.context import RequestContext
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ConflictError, ResourceNotFoundError
from app.shared.permissions import Principal

_RESOURCE = "ai_model_price"


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _row_snapshot(row: AiModelPrice) -> dict[str, Any]:
    """Return a metadata-only dict safe to persist in an audit snapshot."""
    return {
        "provider": row.provider,
        "model": row.model,
        "input_usd_per_1k": float(row.input_usd_per_1k),
        "output_usd_per_1k": float(row.output_usd_per_1k),
        "active": row.active,
        "updated_by": str(row.updated_by) if row.updated_by else None,
    }


async def list_prices(db: AsyncSession) -> list[dict[str, Any]]:
    """Return all price rows ordered by provider, model."""
    result = await db.execute(
        select(AiModelPrice).order_by(AiModelPrice.provider, AiModelPrice.model)
    )
    rows = result.scalars().all()
    return [
        _row_snapshot(r) | {"id": str(r.id), "updated_at": r.updated_at.isoformat()} for r in rows
    ]


async def create_price(
    db: AsyncSession,
    principal: Principal,
    ctx: RequestContext,
    *,
    provider: str,
    model: str,
    input_usd_per_1k: float,
    output_usd_per_1k: float,
    active: bool = True,
) -> dict[str, Any]:
    """Insert a new (provider, model) price row and audit the creation.

    Raises:
        ConflictError: if a row with the same (provider, model) already exists.
    """
    # Pre-check: avoids leaking DB constraint names on duplicate insert.
    existing = await db.execute(
        select(AiModelPrice).where(
            AiModelPrice.provider == provider,
            AiModelPrice.model == model,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "A price entry for this provider and model already exists.",
            details={"provider": provider, "model": model},
        )

    row = AiModelPrice(
        id=uuid.uuid4(),
        provider=provider,
        model=model,
        input_usd_per_1k=input_usd_per_1k,
        output_usd_per_1k=output_usd_per_1k,
        active=active,
        updated_by=principal.user_id,
    )
    db.add(row)
    try:
        await db.flush()  # populate id / server defaults before snapshot
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "A price entry for this provider and model already exists.",
            details={"provider": provider, "model": model},
        ) from None

    after = _row_snapshot(row)
    await write_audit(
        db,
        action="ai_model_price.created",
        resource_type=_RESOURCE,
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        before=None,
        after=after,
    )
    await db.commit()
    await db.refresh(row)
    return _row_snapshot(row) | {"id": str(row.id), "updated_at": row.updated_at.isoformat()}


async def update_price(
    db: AsyncSession,
    principal: Principal,
    ctx: RequestContext,
    price_id: uuid.UUID,
    *,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """Partially update a price row by id and audit the change.

    Raises:
        NotFoundError: if no row with ``price_id`` exists.
    """
    result = await db.execute(select(AiModelPrice).where(AiModelPrice.id == price_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundError(details={"resource": _RESOURCE, "id": str(price_id)})

    before = _row_snapshot(row)

    _ALLOWED = {"input_usd_per_1k", "output_usd_per_1k", "active", "provider", "model"}
    for field, value in fields.items():
        if field in _ALLOWED:
            setattr(row, field, value)

    row.updated_by = principal.user_id
    await db.flush()

    after = _row_snapshot(row)
    await write_audit(
        db,
        action="ai_model_price.updated",
        resource_type=_RESOURCE,
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after=after,
    )
    await db.commit()
    await db.refresh(row)
    return _row_snapshot(row) | {"id": str(row.id), "updated_at": row.updated_at.isoformat()}

"""Industry-taxonomy write use cases (P2/WS2.4 — service-layer RBAC + audit).

The industry taxonomy is a **global** (non-org-scoped) list; reads are public.
Writes are governed by the university control plane: the actor must be a platform
**superadmin** or a member of a **university** org holding the ``taxonomy:manage``
catalog grant. This mirrors ``moderation_service._require_university_moderator``
exactly — a partner Admin holding ``*:*`` matches ``taxonomy:manage`` but is
blocked by the org-type gate, so it can never mutate the shared taxonomy. RBAC is
enforced here (not in the router), and every write is audited.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.opportunities.domain.industry_models import Industry
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "taxonomy"
_MAX_LEVEL = 2  # 3-level hierarchy: 0 (root) / 1 (branch) / 2 (leaf)


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id, actor_org_id=principal.org_id,
        ip=ctx.ip, user_agent=ctx.user_agent,
    )


async def _require_taxonomy_manager(
    session: AsyncSession, principal: Principal
) -> None:
    """Superadmin, or a university-org member holding ``taxonomy:manage``.

    The taxonomy is global so no ``resource_org_id`` is passed; the separate
    university-org gate keeps a wildcard-holding partner Admin out.
    """

    if principal.is_superadmin:
        return
    permission_checker.require(principal, _RESOURCE, "manage")
    if not await org_reporting_facade.is_university_org(session, principal.org_id):
        raise PermissionDeniedError(details={"reason": "university_only"})


async def _get_or_404(session: AsyncSession, industry_id: uuid.UUID) -> Industry:
    row = await session.get(Industry, industry_id)
    if row is None:
        raise ResourceNotFoundError()
    return row


async def create_industry(
    session: AsyncSession,
    *,
    principal: Principal,
    name_vi: str,
    name_en: str,
    slug: str,
    parent_id: uuid.UUID | None,
    sort_order: int,
    ctx: RequestContext,
) -> Industry:
    await _require_taxonomy_manager(session, principal)

    existing = (
        await session.execute(select(Industry.id).where(Industry.slug == slug))
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            "Slug đã tồn tại.", details={"reason": "duplicate_slug"}
        )

    level = 0
    if parent_id is not None:
        parent = await _get_or_404(session, parent_id)
        if parent.level >= _MAX_LEVEL:
            raise ValidationFailedError(
                "Phân cấp ngành tối đa là 3 cấp (0-1-2).",
                details={"reason": "max_depth"},
            )
        level = parent.level + 1

    row = Industry(
        id=uuid.uuid4(), slug=slug, name_vi=name_vi, name_en=name_en,
        level=level, parent_id=parent_id, sort_order=sort_order, is_active=True,
    )
    session.add(row)
    await session.flush()
    await write_audit(
        session, action="industry.created", resource_type="industry",
        resource_id=row.id, context=_audit_ctx(principal, ctx),
        after={"slug": slug, "level": level,
               "parent_id": str(parent_id) if parent_id else None},
    )
    await session.commit()
    await session.refresh(row)
    return row


async def update_industry(
    session: AsyncSession,
    *,
    principal: Principal,
    industry_id: uuid.UUID,
    name_vi: str | None,
    name_en: str | None,
    sort_order: int | None,
    is_active: bool | None,
    ctx: RequestContext,
) -> Industry:
    await _require_taxonomy_manager(session, principal)
    row = await _get_or_404(session, industry_id)

    changed: dict[str, object] = {}
    if name_vi is not None:
        row.name_vi = name_vi
        changed["name_vi"] = name_vi
    if name_en is not None:
        row.name_en = name_en
        changed["name_en"] = name_en
    if sort_order is not None:
        row.sort_order = sort_order
        changed["sort_order"] = sort_order
    if is_active is not None:
        row.is_active = is_active
        changed["is_active"] = is_active

    await session.flush()
    await write_audit(
        session, action="industry.updated", resource_type="industry",
        resource_id=row.id, context=_audit_ctx(principal, ctx),
        after={"fields": sorted(changed.keys())},
    )
    await session.commit()
    await session.refresh(row)
    return row


async def deactivate_industry(
    session: AsyncSession,
    *,
    principal: Principal,
    industry_id: uuid.UUID,
    ctx: RequestContext,
) -> None:
    """Soft-deactivate a node (never hard-delete); refuses if active children remain."""

    await _require_taxonomy_manager(session, principal)
    row = await _get_or_404(session, industry_id)

    active_child = (
        await session.execute(
            select(Industry.id).where(
                Industry.parent_id == row.id, Industry.is_active.is_(True)
            )
        )
    ).scalar_one_or_none()
    if active_child is not None:
        raise ConflictError(
            "Hãy ngừng kích hoạt các ngành con trước.",
            details={"reason": "active_children"},
        )

    if not row.is_active:
        return  # idempotent
    row.is_active = False
    await session.flush()
    await write_audit(
        session, action="industry.deactivated", resource_type="industry",
        resource_id=row.id, context=_audit_ctx(principal, ctx),
        after={"is_active": False},
    )
    await session.commit()

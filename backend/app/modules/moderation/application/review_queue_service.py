"""Human review queue use cases (AI_PRODUCT_SPEC §9.3).

``enqueue`` is the internal write path used by AI safety wiring (bias /
content-moderation / fraud escalation). Listing and resolving are
university-moderator actions — the gate mirrors
``reviews.review_moderation_service._require_university`` (superadmin OR
``jobs:moderate`` + org_type=university).

Every human decision is audited. Findings stored in ``findings_json`` are the
deterministic detectors' structured output — rule metadata only, never raw
prompts, provider internals, or full document text.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.moderation.domain.models import (
    SOURCE_AGENT_LOOP,
    SOURCE_BIAS,
    SOURCE_CONTENT,
    SOURCE_FRAUD,
    SOURCE_MODERATOR_ESCALATION,
    SOURCE_SUPPORT_CASE,
    SOURCE_USER_REPORT,
    STATUS_DISMISSED,
    STATUS_PENDING,
    STATUS_RESOLVED,
    HumanReviewItem,
)

__all__ = [
    "SOURCE_AGENT_LOOP",
    "SOURCE_BIAS",
    "SOURCE_CONTENT",
    "SOURCE_FRAUD",
    "SOURCE_MODERATOR_ESCALATION",
    "SOURCE_SUPPORT_CASE",
    "SOURCE_USER_REPORT",
    "dismiss_item",
    "enqueue",
    "get_source",
    "list_items",
    "list_items_unchecked",
    "resolve_item",
]
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AuthRequiredError,
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.pagination import clamp_limit
from app.shared.permissions import Principal, permission_checker

_ALLOWED_SEVERITIES = frozenset({"high", "medium", "low"})
_ALLOWED_STATUSES = frozenset({STATUS_PENDING, STATUS_RESOLVED, STATUS_DISMISSED})


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def _require_university(session: AsyncSession, principal: Principal) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.is_superadmin:
        return
    if not permission_checker.can(principal, "jobs", "moderate"):
        raise PermissionDeniedError(details={"reason": "university_only"})
    if not await org_reporting_facade.is_university_org(session, principal.org_id):
        raise PermissionDeniedError(details={"reason": "university_only"})


async def enqueue(
    session: AsyncSession,
    *,
    source: str,
    resource_type: str,
    resource_id: uuid.UUID | None,
    org_id: uuid.UUID | None,
    severity: str,
    findings: dict,
) -> HumanReviewItem | None:
    """Persist one escalated AI finding for human review (internal API).

    Idempotent per open item: if a PENDING item already exists for the same
    ``(source, resource_type, resource_id)`` the findings are refreshed on it
    instead of stacking duplicate queue rows (a moderator reviews once).
    Commits its own transaction — callers treat enqueue failure as
    non-fatal advisory degradation, never a user-facing 500.
    """
    if severity not in _ALLOWED_SEVERITIES:
        severity = "medium"

    existing: HumanReviewItem | None = None
    if resource_id is not None:
        existing = (
            await session.execute(
                select(HumanReviewItem).where(
                    HumanReviewItem.source == source,
                    HumanReviewItem.resource_type == resource_type,
                    HumanReviewItem.resource_id == resource_id,
                    HumanReviewItem.status == STATUS_PENDING,
                )
            )
        ).scalar_one_or_none()

    if existing is not None:
        existing.findings_json = findings
        existing.severity = severity
        existing.updated_at = _now()
        await session.commit()
        return existing

    item = HumanReviewItem(
        source=source,
        resource_type=resource_type,
        resource_id=resource_id,
        org_id=org_id,
        severity=severity,
        status=STATUS_PENDING,
        findings_json=findings,
    )
    session.add(item)
    await write_audit(
        session,
        action="moderation.review_item_enqueued",
        resource_type="human_review_item",
        resource_id=item.id,
        after={"source": source, "severity": severity, "target": resource_type},
    )
    await session.commit()
    return item


async def list_items_unchecked(
    session: AsyncSession,
    *,
    status: str | None = None,
    source: str | None = None,
    limit: int = 50,
) -> list[HumanReviewItem]:
    """No-RBAC read seam for a caller that has ALREADY authorized itself under
    a different permission noun (e.g. ``platform_support.support_case_service``
    gates on ``support:read``, not ``jobs:moderate``) — mirrors
    :func:`get_source`. NEVER call this from a router directly.
    """

    stmt = select(HumanReviewItem).order_by(HumanReviewItem.created_at.desc())
    if status:
        if status not in _ALLOWED_STATUSES:
            raise ResourceNotFoundError(details={"reason": "unknown_status"})
        stmt = stmt.where(HumanReviewItem.status == status)
    if source:
        stmt = stmt.where(HumanReviewItem.source == source)
    stmt = stmt.limit(clamp_limit(limit))
    return list((await session.execute(stmt)).scalars().all())


async def list_items(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    source: str | None = None,
    limit: int = 50,
) -> list[HumanReviewItem]:
    await _require_university(session, principal)
    return await list_items_unchecked(session, status=status, source=source, limit=limit)


async def _load_pending(session: AsyncSession, item_id: uuid.UUID) -> HumanReviewItem:
    item = (
        await session.execute(select(HumanReviewItem).where(HumanReviewItem.id == item_id))
    ).scalar_one_or_none()
    if item is None:
        raise ResourceNotFoundError()
    if item.status != STATUS_PENDING:
        raise ConflictError(details={"reason": "already_reviewed"})
    return item


async def _transition(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    item_id: uuid.UUID,
    new_status: str,
    note: str | None,
    skip_permission_check: bool = False,
) -> HumanReviewItem:
    if not skip_permission_check:
        await _require_university(session, principal)
    item = await _load_pending(session, item_id)

    before = {"status": item.status}
    item.status = new_status
    item.resolution_note = (note or "").strip()[:2000] or None
    item.reviewed_by = principal.user_id
    item.reviewed_at = _now()
    item.updated_at = _now()

    await write_audit(
        session,
        action=f"moderation.review_item_{new_status.lower()}",
        resource_type="human_review_item",
        resource_id=item.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after={"status": new_status, "source": item.source},
    )
    await session.commit()
    return item


async def get_source(session: AsyncSession, item_id: uuid.UUID) -> str | None:
    """Cross-module read seam: the ``source`` of one queue row, or ``None``.

    Lets a caller (e.g. ``platform_support.support_case_service``) validate a
    row belongs to its expected ``source`` BEFORE calling :func:`resolve_item`
    / :func:`dismiss_item`, without importing the ``HumanReviewItem`` ORM.
    """

    item = (
        await session.execute(select(HumanReviewItem.source).where(HumanReviewItem.id == item_id))
    ).scalar_one_or_none()
    return item


async def resolve_item(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    item_id: uuid.UUID,
    note: str | None = None,
    skip_permission_check: bool = False,
) -> HumanReviewItem:
    """Moderator confirms the finding and has acted on it (outside this table).

    ``skip_permission_check`` is for a trusted caller that has ALREADY
    authorized itself under a different permission noun (e.g.
    ``platform_support.support_case_service`` gates on ``support:act``, not
    ``jobs:moderate``) — mirrors :func:`list_items_unchecked`. NEVER pass
    ``True`` from a router directly.
    """
    return await _transition(
        session,
        principal=principal,
        ctx=ctx,
        item_id=item_id,
        new_status=STATUS_RESOLVED,
        note=note,
        skip_permission_check=skip_permission_check,
    )


async def dismiss_item(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    item_id: uuid.UUID,
    note: str | None = None,
) -> HumanReviewItem:
    """Moderator judges the AI finding a false positive — human override.

    Dismissals feed the "human override rate" SLO (§10.4): a rate above 30%
    signals detector precision problems.
    """
    return await _transition(
        session,
        principal=principal,
        ctx=ctx,
        item_id=item_id,
        new_status=STATUS_DISMISSED,
        note=note,
    )

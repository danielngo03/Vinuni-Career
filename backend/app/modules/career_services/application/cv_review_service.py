"""CV review queue: assignment, feedback, and status lifecycle (B-554).

RBAC resource: ``career_services_cv_review``. ``cv_id`` is a bare reference to
``documents.cv_profiles`` (no cross-module ORM join — the CV content itself is
read through the ``documents`` module's own RBAC'd surface); this queue only
tracks the review workflow metadata.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.career_services.application.common import audit_ctx, require_org
from app.modules.career_services.domain import catalog
from app.modules.career_services.domain.models import CvReviewQueueItem
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "career_services_cv_review"


def _presenter(item: CvReviewQueueItem, *, locale: str = "vi") -> dict:
    return {
        "id": str(item.id),
        "student_id": str(item.student_id),
        "cv_id": str(item.cv_id) if item.cv_id else None,
        "requested_by": str(item.requested_by),
        "assigned_counselor_id": (
            str(item.assigned_counselor_id) if item.assigned_counselor_id else None
        ),
        "status": item.status,
        "status_label": catalog.cv_review_status_label(item.status, locale=locale),
        "priority": item.priority,
        "priority_label": catalog.cv_review_priority_label(item.priority, locale=locale),
        "feedback": item.feedback,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
    }


async def _get_item(
    session: AsyncSession, *, org_id: uuid.UUID, item_id: uuid.UUID
) -> CvReviewQueueItem | None:
    stmt = select(CvReviewQueueItem).where(
        CvReviewQueueItem.id == item_id, CvReviewQueueItem.org_id == org_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_item(
    session: AsyncSession,
    *,
    principal: Principal,
    student_id: uuid.UUID,
    cv_id: uuid.UUID | None,
    priority: str,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "create", resource_org_id=org_id)
    if priority not in catalog.CV_REVIEW_PRIORITIES:
        raise ValidationFailedError(details={"reason": "invalid_priority"})

    item = CvReviewQueueItem(
        org_id=org_id,
        student_id=student_id,
        cv_id=cv_id,
        requested_by=principal.user_id,
        status=catalog.CV_REVIEW_QUEUED,
        priority=priority,
    )
    session.add(item)
    await session.flush()
    await write_audit(
        session,
        action="career_services.cv_review.created",
        resource_type="career_services_cv_review_item",
        resource_id=item.id,
        context=audit_ctx(principal, ctx),
        after={"student_id": str(student_id), "priority": priority},
    )
    await session.commit()
    return _presenter(item, locale=locale)


async def list_items(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    assigned_counselor_id: uuid.UUID | None = None,
    locale: str = "vi",
) -> list[dict]:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=org_id)
    stmt = select(CvReviewQueueItem).where(CvReviewQueueItem.org_id == org_id)
    if status is not None:
        if status not in catalog.CV_REVIEW_STATUSES:
            raise ValidationFailedError(details={"reason": "invalid_status"})
        stmt = stmt.where(CvReviewQueueItem.status == status)
    if assigned_counselor_id is not None:
        stmt = stmt.where(CvReviewQueueItem.assigned_counselor_id == assigned_counselor_id)
    stmt = stmt.order_by(CvReviewQueueItem.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [_presenter(i, locale=locale) for i in rows]


async def assign_counselor(
    session: AsyncSession,
    *,
    principal: Principal,
    item_id: uuid.UUID,
    counselor_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "assign", resource_org_id=org_id)
    item = await _get_item(session, org_id=org_id, item_id=item_id)
    if item is None:
        raise ResourceNotFoundError()
    item.assigned_counselor_id = counselor_id
    if item.status == catalog.CV_REVIEW_QUEUED:
        item.status = catalog.CV_REVIEW_IN_REVIEW
    await session.flush()
    await session.refresh(item)
    await write_audit(
        session,
        action="career_services.cv_review.assigned",
        resource_type="career_services_cv_review_item",
        resource_id=item.id,
        context=audit_ctx(principal, ctx),
        after={"counselor_id": str(counselor_id)},
    )
    await session.commit()
    return _presenter(item, locale=locale)


async def update_status(
    session: AsyncSession,
    *,
    principal: Principal,
    item_id: uuid.UUID,
    status: str,
    feedback: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "update", resource_org_id=org_id)
    item = await _get_item(session, org_id=org_id, item_id=item_id)
    if item is None:
        raise ResourceNotFoundError()
    if status not in catalog.CV_REVIEW_STATUSES:
        raise ValidationFailedError(details={"reason": "invalid_status"})
    if feedback is not None:
        item.feedback = feedback
    item.status = status
    if status in (catalog.CV_REVIEW_APPROVED, catalog.CV_REVIEW_CLOSED):
        from datetime import UTC, datetime

        item.resolved_at = datetime.now(tz=UTC)
    await session.flush()
    await session.refresh(item)
    await write_audit(
        session,
        action="career_services.cv_review.status_changed",
        resource_type="career_services_cv_review_item",
        resource_id=item.id,
        context=audit_ctx(principal, ctx),
        after={"status": status},
    )
    await session.commit()
    return _presenter(item, locale=locale)

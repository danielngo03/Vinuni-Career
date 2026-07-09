"""University review-moderation use cases (ADR-0013).

University-only (gate mirrors `dashboards.university_dashboard._require_university`
— superadmin OR `jobs:moderate` + org_type=university; a dedicated
`reviews:moderate` grant is a later refinement, ADR-0013 open-Q #3). Publish a
pending review, remove a published/flagged one (reason POLICY-GATED at the service
layer — a genuinely negative opinion is non-removable), restore, or force-flag.
Every transition is audited and recomputes the org rating projection.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.organization.application import org_reporting_facade
from app.modules.reviews.api import presenters
from app.modules.reviews.application import rating_projection
from app.modules.reviews.application.errors import (
    RemovalReasonInvalidError,
    ReviewStateConflictError,
)
from app.modules.reviews.domain import entities
from app.modules.reviews.domain.models import CompanyReview, ReviewRating
from app.modules.users.application import student_directory_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.pagination import clamp_limit
from app.shared.permissions import Principal, permission_checker


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
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "university_only"})


async def _load(session: AsyncSession, review_id: uuid.UUID) -> CompanyReview:
    review = (
        await session.execute(
            select(CompanyReview).where(
                CompanyReview.id == review_id,
                CompanyReview.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if review is None:
        raise ResourceNotFoundError()
    return review


async def _rating(session: AsyncSession, review_id: uuid.UUID) -> ReviewRating:
    return (
        await session.execute(select(ReviewRating).where(ReviewRating.review_id == review_id))
    ).scalar_one()


async def list_queue(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> dict:
    await _require_university(session, principal)
    page_limit = clamp_limit(limit)
    filters: list[ColumnElement[bool]] = [CompanyReview.deleted_at.is_(None)]
    if status is not None:
        if status not in entities.ALL_STATUSES:
            from app.modules.reviews.application.errors import InvalidReviewFieldError

            raise InvalidReviewFieldError("status")
        filters.append(CompanyReview.status == status)

    rows = (
        await session.execute(
            select(CompanyReview, ReviewRating)
            .join(ReviewRating, ReviewRating.review_id == CompanyReview.id)
            .where(*filters)
            .order_by(
                CompanyReview.report_count.desc(),
                CompanyReview.created_at.desc(),
            )
            .limit(page_limit)
        )
    ).all()
    total = (
        await session.execute(select(func.count()).select_from(CompanyReview).where(*filters))
    ).scalar_one()
    pending = (
        await session.execute(
            select(func.count())
            .select_from(CompanyReview)
            .where(
                CompanyReview.deleted_at.is_(None),
                CompanyReview.status == entities.STATUS_PENDING,
            )
        )
    ).scalar_one()
    flagged = (
        await session.execute(
            select(func.count())
            .select_from(CompanyReview)
            .where(
                CompanyReview.deleted_at.is_(None),
                CompanyReview.status == entities.STATUS_FLAGGED,
            )
        )
    ).scalar_one()

    # Moderators always see author identity (accountability), even if anonymous.
    names = await student_directory_facade.display_for(
        session, [r.reviewer_id for (r, _rt) in rows], locale=locale
    )
    items = [
        presenters.review_moderation(
            review,
            rating,
            author_name=names.get(review.reviewer_id),
            locale=locale,
        )
        for (review, rating) in rows
    ]
    return {
        "items": items,
        "total": int(total),
        "counts": {"pending": int(pending), "flagged": int(flagged)},
    }


async def publish_review(
    session: AsyncSession,
    *,
    principal: Principal,
    review_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_university(session, principal)
    review = await _load(session, review_id)
    if review.status == entities.STATUS_PUBLISHED:
        return await _present(session, review, locale=locale)  # idempotent
    if review.status not in (entities.STATUS_PENDING, entities.STATUS_FLAGGED):
        raise ReviewStateConflictError()
    review.status = entities.STATUS_PUBLISHED
    review.published_at = _now()
    review.moderated_by = principal.user_id
    review.moderated_at = _now()
    review.version += 1
    await write_audit(
        session,
        action="review.published",
        resource_type="company_review",
        resource_id=review.id,
        context=_audit_ctx(principal, ctx),
        after={"status": review.status, "org_id": str(review.org_id)},
    )
    await rating_projection.recompute(session, review.org_id)
    await session.commit()
    return await _present(session, review, locale=locale)


async def remove_review(
    session: AsyncSession,
    *,
    principal: Principal,
    review_id: uuid.UUID,
    reason: str,
    note: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_university(session, principal)
    # Policy gate: only allowed removal grounds — negative opinion is NOT one.
    if reason not in entities.REMOVAL_REASONS:
        raise RemovalReasonInvalidError()
    review = await _load(session, review_id)
    if review.status == entities.STATUS_REMOVED:
        return await _present(session, review, locale=locale)  # idempotent
    before = review.status
    review.status = entities.STATUS_REMOVED
    review.moderation_note = note
    review.moderated_by = principal.user_id
    review.moderated_at = _now()
    review.version += 1
    await write_audit(
        session,
        action="review.removed",
        resource_type="company_review",
        resource_id=review.id,
        context=_audit_ctx(principal, ctx),
        before={"status": before},
        after={"status": review.status, "reason": reason, "org_id": str(review.org_id)},
    )
    await rating_projection.recompute(session, review.org_id)
    await session.commit()
    return await _present(session, review, locale=locale)


async def restore_review(
    session: AsyncSession,
    *,
    principal: Principal,
    review_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_university(session, principal)
    review = await _load(session, review_id)
    if review.status == entities.STATUS_PUBLISHED:
        return await _present(session, review, locale=locale)
    review.status = entities.STATUS_PUBLISHED
    review.published_at = review.published_at or _now()
    review.moderated_by = principal.user_id
    review.moderated_at = _now()
    review.version += 1
    await write_audit(
        session,
        action="review.restored",
        resource_type="company_review",
        resource_id=review.id,
        context=_audit_ctx(principal, ctx),
        after={"status": review.status, "org_id": str(review.org_id)},
    )
    await rating_projection.recompute(session, review.org_id)
    await session.commit()
    return await _present(session, review, locale=locale)


async def _present(session: AsyncSession, review: CompanyReview, *, locale: str) -> dict:
    rating = await _rating(session, review.id)
    names = await student_directory_facade.display_for(session, [review.reviewer_id], locale=locale)
    return presenters.review_moderation(
        review, rating, author_name=names.get(review.reviewer_id), locale=locale
    )

"""Student-facing company-review use cases (ADR-0013).

Owns submit / read-own / edit / delete / report and the public published list.
RBAC, eligibility, content validation, idempotent dedupe, audit, and the
synchronous rating-projection recompute all live here (routers are HTTP-only).
Cross-module reads (org slug→id, author display, eligibility) go through facades
— this module imports no other module's ORM.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.organization.application import org_lookup_facade
from app.modules.recruitment.application import review_eligibility_facade
from app.modules.reviews.api import presenters
from app.modules.reviews.application import rating_projection
from app.modules.reviews.application.errors import (
    InsufficientReviewContentError,
    InvalidReviewFieldError,
    ReviewAlreadyExistsError,
    ReviewSelfNotAllowedError,
    ReviewStateConflictError,
)
from app.modules.reviews.domain import entities
from app.modules.reviews.domain.models import (
    CompanyReview,
    ReviewHelpfulVote,
    ReviewRating,
    ReviewReport,
)
from app.modules.users.application import student_directory_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AuthRequiredError,
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.pagination import clamp_limit

EDIT_WINDOW = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _audit_ctx(principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _require_student(principal) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.persona != "student" and not principal.is_superadmin:
        raise PermissionDeniedError(details={"reason": "students_only"})


def _validate_content(payload: dict) -> None:
    title = (payload.get("title") or "").strip()
    body = (payload.get("body") or "").strip()
    if not title or len(title) > entities.TITLE_MAX:
        raise InvalidReviewFieldError("title")
    if len(body) < entities.BODY_MIN:
        raise InsufficientReviewContentError()
    if len(body) > entities.BODY_MAX:
        raise InvalidReviewFieldError("body")
    for cat in entities.RATING_CATEGORIES:
        if not entities.is_rating(payload.get(cat)):
            raise InvalidReviewFieldError(cat)
    iv = payload.get("interview_experience")
    if iv is not None and not entities.is_rating(iv):
        raise InvalidReviewFieldError("interview_experience")


async def _load_owned(
    session: AsyncSession, *, review_id: uuid.UUID, principal
) -> CompanyReview:
    review = (
        await session.execute(
            select(CompanyReview).where(
                CompanyReview.id == review_id,
                CompanyReview.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    # Non-author → 404 (enumeration-safe).
    if review is None or review.reviewer_id != principal.user_id:
        raise ResourceNotFoundError()
    return review


async def _rating_for(session: AsyncSession, review_id: uuid.UUID) -> ReviewRating:
    return (
        await session.execute(
            select(ReviewRating).where(ReviewRating.review_id == review_id)
        )
    ).scalar_one()


async def _resolve_org(session: AsyncSession, slug: str) -> uuid.UUID:
    org_id = await org_lookup_facade.listable_id_for_slug(session, slug=slug)
    if org_id is None:
        raise ResourceNotFoundError()
    return org_id


# --------------------------------------------------------------------------- #
# Submit / read-own / edit / delete                                           #
# --------------------------------------------------------------------------- #


async def submit_review(
    session: AsyncSession,
    *,
    principal,
    slug: str,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    _require_student(principal)
    org_id = await _resolve_org(session, slug)
    if principal.org_id is not None and principal.org_id == org_id:
        raise ReviewSelfNotAllowedError()

    elig = await review_eligibility_facade.eligibility_for(
        session, user_id=principal.user_id, org_id=org_id
    )
    if elig is None or elig[0] not in entities.ACCEPTED_ELIGIBILITY:
        from app.modules.reviews.application.errors import ReviewNotEligibleError

        raise ReviewNotEligibleError()
    eligibility_type, application_id = elig

    _validate_content(payload)

    # Dedupe: any existing row (incl. soft-deleted) for (org, reviewer) blocks a 2nd.
    existing = (
        await session.execute(
            select(CompanyReview.id).where(
                CompanyReview.org_id == org_id,
                CompanyReview.reviewer_id == principal.user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ReviewAlreadyExistsError()

    review = CompanyReview(
        org_id=org_id,
        reviewer_id=principal.user_id,
        eligibility_type=eligibility_type,
        application_id=application_id,
        title=payload["title"].strip(),
        body=payload["body"].strip(),
        pros=(payload.get("pros") or None),
        cons=(payload.get("cons") or None),
        is_anonymous=bool(payload.get("is_anonymous", False)),
        status=entities.STATUS_PENDING,
    )
    session.add(review)
    await session.flush()
    session.add(
        ReviewRating(
            review_id=review.id,
            overall=payload["overall"],
            work_life_balance=payload["work_life_balance"],
            culture_values=payload["culture_values"],
            compensation=payload["compensation"],
            career_growth=payload["career_growth"],
            interview_experience=payload.get("interview_experience"),
        )
    )
    await write_audit(
        session, action="review.created", resource_type="company_review",
        resource_id=review.id, context=_audit_ctx(principal, ctx),
        after={"org_id": str(org_id), "status": review.status,
               "eligibility_type": eligibility_type},
    )
    await session.commit()
    await session.refresh(review)
    rating = await _rating_for(session, review.id)
    return presenters.review_owner(review, rating, locale=locale)


async def get_my_review(
    session: AsyncSession, *, principal, slug: str, locale: str = "vi"
) -> dict:
    _require_student(principal)
    org_id = await _resolve_org(session, slug)
    review = (
        await session.execute(
            select(CompanyReview).where(
                CompanyReview.org_id == org_id,
                CompanyReview.reviewer_id == principal.user_id,
                CompanyReview.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if review is None:
        raise ResourceNotFoundError()
    rating = await _rating_for(session, review.id)
    return presenters.review_owner(review, rating, locale=locale)


async def update_review(
    session: AsyncSession,
    *,
    principal,
    review_id: uuid.UUID,
    payload: dict,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    _require_student(principal)
    review = await _load_owned(session, review_id=review_id, principal=principal)
    if version is not None and version != review.version:
        raise ReviewStateConflictError()
    if _now() - review.created_at.replace(tzinfo=UTC) > EDIT_WINDOW:
        raise ConflictError(
            "Đã quá thời hạn chỉnh sửa đánh giá (30 ngày).",
            details={"reason": "edit_window_closed"},
        )
    _validate_content(payload)

    was_published = review.status == entities.STATUS_PUBLISHED
    review.title = payload["title"].strip()
    review.body = payload["body"].strip()
    review.pros = payload.get("pros") or None
    review.cons = payload.get("cons") or None
    review.is_anonymous = bool(payload.get("is_anonymous", review.is_anonymous))
    # Editing re-enters moderation (pre-moderation model).
    review.status = entities.STATUS_PENDING
    review.published_at = None
    review.version += 1

    rating = await _rating_for(session, review.id)
    rating.overall = payload["overall"]
    rating.work_life_balance = payload["work_life_balance"]
    rating.culture_values = payload["culture_values"]
    rating.compensation = payload["compensation"]
    rating.career_growth = payload["career_growth"]
    rating.interview_experience = payload.get("interview_experience")

    await write_audit(
        session, action="review.updated", resource_type="company_review",
        resource_id=review.id, context=_audit_ctx(principal, ctx),
        after={"status": review.status},
    )
    # An edit pulls a previously-published review out of the public set.
    if was_published:
        await rating_projection.recompute(session, review.org_id)
    await session.commit()
    await session.refresh(review)
    rating = await _rating_for(session, review.id)
    return presenters.review_owner(review, rating, locale=locale)


async def delete_review(
    session: AsyncSession, *, principal, review_id: uuid.UUID, ctx: RequestContext
) -> None:
    _require_student(principal)
    review = await _load_owned(session, review_id=review_id, principal=principal)
    was_published = review.status == entities.STATUS_PUBLISHED
    review.deleted_at = _now()
    await write_audit(
        session, action="review.deleted", resource_type="company_review",
        resource_id=review.id, context=_audit_ctx(principal, ctx),
        before={"status": review.status},
    )
    if was_published:
        await rating_projection.recompute(session, review.org_id)
    await session.commit()


# --------------------------------------------------------------------------- #
# Report                                                                       #
# --------------------------------------------------------------------------- #


async def report_review(
    session: AsyncSession,
    *,
    principal,
    review_id: uuid.UUID,
    reason_code: str,
    note: str | None = None,
    ctx: RequestContext,
) -> dict:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if reason_code not in entities.REPORT_REASONS:
        raise InvalidReviewFieldError("reason_code")
    review = (
        await session.execute(
            select(CompanyReview).where(
                CompanyReview.id == review_id,
                CompanyReview.status == entities.STATUS_PUBLISHED,
                CompanyReview.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if review is None:
        raise ResourceNotFoundError()

    dup = (
        await session.execute(
            select(ReviewReport.id).where(
                ReviewReport.review_id == review_id,
                ReviewReport.reporter_id == principal.user_id,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        return {"status": "already_reported"}  # idempotent

    session.add(
        ReviewReport(
            review_id=review_id,
            reporter_id=principal.user_id,
            reporter_org_id=principal.org_id,
            reason_code=reason_code,
            note=note,
        )
    )
    review.report_count += 1
    # First report flags for moderator attention but keeps the review PUBLISHED
    # (only a moderator removal drops it from the aggregate — ADR-0013 §8).
    if review.status == entities.STATUS_PUBLISHED:
        review.status = entities.STATUS_FLAGGED
    await write_audit(
        session, action="review.reported", resource_type="company_review",
        resource_id=review_id, context=_audit_ctx(principal, ctx),
        after={"reason_code": reason_code},
    )
    await session.commit()
    return {"status": "reported"}


# --------------------------------------------------------------------------- #
# Public published list                                                        #
# --------------------------------------------------------------------------- #

# Published OR flagged stay publicly visible (flagged = reported-but-not-removed).
_PUBLIC_VISIBLE = (entities.STATUS_PUBLISHED, entities.STATUS_FLAGGED)


async def list_public_reviews(
    session: AsyncSession,
    *,
    slug: str,
    principal=None,
    limit: int | None = None,
    locale: str = "vi",
) -> dict:
    org_id = await _resolve_org(session, slug)
    page_limit = clamp_limit(limit)
    rows = (
        await session.execute(
            select(CompanyReview, ReviewRating)
            .join(ReviewRating, ReviewRating.review_id == CompanyReview.id)
            .where(
                CompanyReview.org_id == org_id,
                CompanyReview.status.in_(_PUBLIC_VISIBLE),
                CompanyReview.deleted_at.is_(None),
            )
            .order_by(CompanyReview.published_at.desc().nulls_last(),
                      CompanyReview.id.desc())
            .limit(page_limit)
        )
    ).all()

    # Resolve display names only for NON-anonymous authors (anonymity = no PII out).
    named_ids = [r.reviewer_id for (r, _rt) in rows if not r.is_anonymous]
    names = await student_directory_facade.display_for(
        session, named_ids, locale=locale
    )

    # Resolve caller's votes when authenticated.
    voter_set: set[uuid.UUID] = set()
    is_authed = principal is not None and getattr(principal, "is_authenticated", False)
    if is_authed and principal.user_id:
        review_ids = [r.id for (r, _rt) in rows]
        if review_ids:
            vote_rows = (
                await session.execute(
                    select(ReviewHelpfulVote.review_id).where(
                        ReviewHelpfulVote.voter_id == principal.user_id,
                        ReviewHelpfulVote.review_id.in_(review_ids),
                    )
                )
            ).scalars().all()
            voter_set = set(vote_rows)

    items = [
        presenters.review_public(
            review, rating,
            author_name=names.get(review.reviewer_id),
            locale=locale,
            my_vote=(review.id in voter_set) if (voter_set or is_authed) else None,
        )
        for (review, rating) in rows
    ]
    return {"items": items, "count": len(items)}


# --------------------------------------------------------------------------- #
# Helpfulness voting                                                           #
# --------------------------------------------------------------------------- #


async def _load_published_review(
    session: AsyncSession, review_id: uuid.UUID
) -> CompanyReview:
    review = (
        await session.execute(
            select(CompanyReview).where(
                CompanyReview.id == review_id,
                CompanyReview.status.in_(_PUBLIC_VISIBLE),
                CompanyReview.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if review is None:
        raise ResourceNotFoundError()
    return review


async def vote_helpful(
    session: AsyncSession,
    *,
    principal,
    review_id: uuid.UUID,
) -> dict:
    """Mark a published review as helpful. Idempotent — double-voting is a no-op."""
    if not principal.is_authenticated or principal.user_id is None:
        raise AuthRequiredError()

    review = await _load_published_review(session, review_id)

    # Block reviewer from voting their own review.
    if review.reviewer_id == principal.user_id:
        raise ConflictError("Cannot vote on own review.")

    existing = (
        await session.execute(
            select(ReviewHelpfulVote).where(
                ReviewHelpfulVote.review_id == review_id,
                ReviewHelpfulVote.voter_id == principal.user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"helpful_count": review.helpful_count, "my_vote": True}

    session.add(ReviewHelpfulVote(
        id=uuid.uuid4(),
        review_id=review_id,
        voter_id=principal.user_id,
    ))
    review.helpful_count += 1
    await session.commit()
    return {"helpful_count": review.helpful_count, "my_vote": True}


async def remove_helpful_vote(
    session: AsyncSession,
    *,
    principal,
    review_id: uuid.UUID,
) -> dict:
    """Remove a helpfulness vote. Idempotent — removing a non-existent vote is a no-op."""
    if not principal.is_authenticated or principal.user_id is None:
        raise AuthRequiredError()

    review = await _load_published_review(session, review_id)

    existing = (
        await session.execute(
            select(ReviewHelpfulVote).where(
                ReviewHelpfulVote.review_id == review_id,
                ReviewHelpfulVote.voter_id == principal.user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        return {"helpful_count": review.helpful_count, "my_vote": False}

    await session.delete(existing)
    review.helpful_count = max(0, review.helpful_count - 1)
    await session.commit()
    return {"helpful_count": review.helpful_count, "my_vote": False}


# --------------------------------------------------------------------------- #
# Partner response                                                             #
# --------------------------------------------------------------------------- #

_PARTNER_RESPONSE_MAX = 2000
_PARTNER_RESPONSE_MIN = 10


async def add_partner_response(
    session: AsyncSession,
    *,
    principal,
    review_id: uuid.UUID,
    response_text: str,
    ctx: RequestContext,
) -> dict:
    """Partner admin / owner adds or updates their public response to a published review."""
    if not principal.is_authenticated or principal.org_id is None:
        raise AuthRequiredError()

    response_text = response_text.strip()
    if len(response_text) < _PARTNER_RESPONSE_MIN:
        raise InvalidReviewFieldError("response")
    if len(response_text) > _PARTNER_RESPONSE_MAX:
        raise InvalidReviewFieldError("response")

    review = (
        await session.execute(
            select(CompanyReview).where(
                CompanyReview.id == review_id,
                CompanyReview.org_id == principal.org_id,
                CompanyReview.status.in_(_PUBLIC_VISIBLE),
                CompanyReview.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if review is None:
        raise ResourceNotFoundError()

    review.partner_response = response_text
    review.partner_response_at = _now()
    await write_audit(
        session, action="review.partner_response_added",
        resource_type="company_review", resource_id=review_id,
        context=_audit_ctx(principal, ctx),
    )
    await session.commit()
    return {"status": "ok"}

"""Company reviews (Module 13 / ADR-0013) — eligibility, moderation, aggregate.

Proves the slice-1 invariants end-to-end through the real service path:
- interaction-gated eligibility (ineligible student 403);
- one-review-per-student-per-company (409, even if soft-deleted);
- pre-moderation: a review is `pending` until a university moderator publishes;
- the rating projection aggregates only PUBLISHED reviews (Bayesian), recomputes
  on publish/remove/edit, and is idempotent;
- anonymity = no author PII in the public payload;
- removal is policy-gated (a non-allowed reason is rejected) + RBAC university-only;
- non-listable org slug → 404.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.organization.application import company_directory_service
from app.modules.organization.domain.models import Organization
from app.modules.recruitment.application import access
from app.modules.reviews.application import (
    company_rating_facade,
    rating_projection,
    review_moderation_service,
    review_service,
)
from app.modules.reviews.application.errors import (
    RemovalReasonInvalidError,
    ReviewAlreadyExistsError,
    ReviewNotEligibleError,
)
from app.modules.reviews.domain import entities
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.integration.test_recruitment_offers import _setup_reviewed
from tests.org_utils import make_org_with_admin


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


_BODY = "This was a solid internship experience with real engineering mentorship."


def _payload(**over) -> dict:
    base = {
        "title": "Great place to learn",
        "body": _BODY,
        "pros": "Mentorship",
        "cons": "Fast pace",
        "is_anonymous": False,
        "overall": 5,
        "work_life_balance": 4,
        "culture_values": 5,
        "compensation": 3,
        "career_growth": 5,
        "interview_experience": 4,
    }
    base.update(over)
    return base


async def _org_slug(db, org_id: uuid.UUID) -> str:
    return (
        await db.execute(select(Organization.slug).where(Organization.id == org_id))
    ).scalar_one()


async def _eligible_setup(db):
    """partner principal, student (eligible: app under_review), org slug."""
    partner, _su, student, _job, _app = await _setup_reviewed(db)
    slug = await _org_slug(db, partner.org_id)
    return partner, student, slug


# --------------------------------------------------------------------------- #
# Submit + eligibility + dedupe                                               #
# --------------------------------------------------------------------------- #


async def test_submit_eligible_creates_pending(db_session) -> None:
    _partner, student, slug = await _eligible_setup(db_session)
    out = await review_service.submit_review(
        db_session, principal=student, slug=slug, payload=_payload(), ctx=CTX
    )
    assert out["status"] == entities.STATUS_PENDING
    assert out["ratings"]["overall"] == 5
    assert out["trust_label"]  # friendly, not a raw enum
    assert "system_verified" not in str(out)


async def test_submit_ineligible_forbidden(db_session) -> None:
    _partner, _student, slug = await _eligible_setup(db_session)
    _su, stranger = await make_student(db_session, prefix="stranger")
    with pytest.raises(ReviewNotEligibleError):
        await review_service.submit_review(
            db_session, principal=stranger, slug=slug, payload=_payload(), ctx=CTX
        )


async def test_one_review_per_company(db_session) -> None:
    _partner, student, slug = await _eligible_setup(db_session)
    await review_service.submit_review(
        db_session, principal=student, slug=slug, payload=_payload(), ctx=CTX
    )
    with pytest.raises(ReviewAlreadyExistsError):
        await review_service.submit_review(
            db_session, principal=student, slug=slug, payload=_payload(), ctx=CTX
        )


async def test_nonlistable_slug_404(db_session) -> None:
    _uu, uorg, _uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="s404")
    slug = await _org_slug(db_session, uorg.id)
    with pytest.raises(ResourceNotFoundError):
        await review_service.submit_review(
            db_session, principal=student, slug=slug, payload=_payload(), ctx=CTX
        )


# --------------------------------------------------------------------------- #
# Moderation: publish -> aggregate, RBAC, policy gate                         #
# --------------------------------------------------------------------------- #


async def test_publish_builds_aggregate_and_profile(db_session) -> None:
    partner, student, slug = await _eligible_setup(db_session)
    sub = await review_service.submit_review(
        db_session, principal=student, slug=slug, payload=_payload(overall=5), ctx=CTX
    )
    review_id = uuid.UUID(sub["id"])

    # Not in the aggregate while pending.
    pre = await company_rating_facade.ratings_for(db_session, [partner.org_id])
    assert pre == {}

    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    pub = await review_moderation_service.publish_review(
        db_session, principal=uni, review_id=review_id, ctx=CTX
    )
    assert pub["status"] == entities.STATUS_PUBLISHED

    post = await company_rating_facade.ratings_for(db_session, [partner.org_id])
    block = post[partner.org_id]
    assert block["review_count"] == 1
    assert block["overall_avg"] == 3.5  # Bayesian: (5 + 3*3)/(1+3)
    assert block["distribution"]["5"] == 1

    # Public company profile surfaces the rating block.
    profile = await company_directory_service.get_company(db_session, slug=slug)
    assert profile["rating"]["review_count"] == 1


async def test_moderation_is_university_only(db_session) -> None:
    partner, student, slug = await _eligible_setup(db_session)
    sub = await review_service.submit_review(
        db_session, principal=student, slug=slug, payload=_payload(), ctx=CTX
    )
    rid = uuid.UUID(sub["id"])
    # Partner (the admin principal) cannot moderate.
    with pytest.raises(PermissionDeniedError):
        await review_moderation_service.publish_review(
            db_session, principal=partner, review_id=rid, ctx=CTX
        )
    # Student cannot moderate.
    with pytest.raises(PermissionDeniedError):
        await review_moderation_service.list_queue(db_session, principal=student)


async def test_remove_policy_gate(db_session) -> None:
    partner, student, slug = await _eligible_setup(db_session)
    sub = await review_service.submit_review(
        db_session, principal=student, slug=slug, payload=_payload(), ctx=CTX
    )
    rid = uuid.UUID(sub["id"])
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    await review_moderation_service.publish_review(
        db_session, principal=uni, review_id=rid, ctx=CTX
    )

    # A merely-negative-opinion reason is NOT an allowed removal ground.
    with pytest.raises(RemovalReasonInvalidError):
        await review_moderation_service.remove_review(
            db_session,
            principal=uni,
            review_id=rid,
            reason="negative_opinion",
            ctx=CTX,
        )
    # A policy reason removes it and drops it from the aggregate.
    await review_moderation_service.remove_review(
        db_session, principal=uni, review_id=rid, reason="pii", ctx=CTX
    )
    agg = await company_rating_facade.ratings_for(db_session, [partner.org_id])
    assert agg == {}


# --------------------------------------------------------------------------- #
# Anonymity + projection idempotency                                          #
# --------------------------------------------------------------------------- #


async def test_anonymous_review_has_no_author_pii(db_session) -> None:
    _partner, student, slug = await _eligible_setup(db_session)
    sub = await review_service.submit_review(
        db_session,
        principal=student,
        slug=slug,
        payload=_payload(is_anonymous=True),
        ctx=CTX,
    )
    rid = uuid.UUID(sub["id"])
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    await review_moderation_service.publish_review(
        db_session, principal=uni, review_id=rid, ctx=CTX
    )
    pub = await review_service.list_public_reviews(db_session, slug=slug)
    item = pub["items"][0]
    assert item["is_anonymous"] is True
    assert "reviewer_id" not in item
    assert str(student.user_id) not in str(item)
    assert item["author_name"] in {"Ứng viên ẩn danh", "Anonymous candidate"}


async def test_projection_idempotent(db_session) -> None:
    partner, student, slug = await _eligible_setup(db_session)
    sub = await review_service.submit_review(
        db_session, principal=student, slug=slug, payload=_payload(), ctx=CTX
    )
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    await review_moderation_service.publish_review(
        db_session, principal=uni, review_id=uuid.UUID(sub["id"]), ctx=CTX
    )
    first = await rating_projection.recompute(db_session, partner.org_id)
    second = await rating_projection.recompute(db_session, partner.org_id)
    assert first["review_count"] == second["review_count"] == 1
    assert first["overall_avg"] == second["overall_avg"]


async def test_edit_pulls_published_review_from_aggregate(db_session) -> None:
    partner, student, slug = await _eligible_setup(db_session)
    sub = await review_service.submit_review(
        db_session, principal=student, slug=slug, payload=_payload(), ctx=CTX
    )
    rid = uuid.UUID(sub["id"])
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    await review_moderation_service.publish_review(
        db_session, principal=uni, review_id=rid, ctx=CTX
    )
    assert (await company_rating_facade.ratings_for(db_session, [partner.org_id]))[partner.org_id][
        "review_count"
    ] == 1

    # Editing re-enters pending and removes it from the public aggregate.
    edited = await review_service.update_review(
        db_session,
        principal=student,
        review_id=rid,
        payload=_payload(title="Updated thoughts"),
        ctx=CTX,
    )
    assert edited["status"] == entities.STATUS_PENDING
    assert await company_rating_facade.ratings_for(db_session, [partner.org_id]) == {}


async def test_flagged_review_stays_in_aggregate(db_session) -> None:
    """ADR-0013: a reported (flagged) review stays in the public aggregate.

    Report spam cannot suppress a legitimate negative review from the rating.
    """
    partner, student, slug = await _eligible_setup(db_session)
    sub = await review_service.submit_review(
        db_session, principal=student, slug=slug, payload=_payload(overall=4), ctx=CTX
    )
    rid = uuid.UUID(sub["id"])
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    await review_moderation_service.publish_review(
        db_session, principal=uni, review_id=rid, ctx=CTX
    )

    # Aggregate counts the published review.
    pre = await company_rating_facade.ratings_for(db_session, [partner.org_id])
    assert pre[partner.org_id]["review_count"] == 1

    # A different student reports the review → status becomes FLAGGED.
    _su2, reporter = await make_student(db_session, prefix="reporter")
    # Grant the reporter an eligible relationship so reporting isn't blocked.
    # (report_review only requires authentication, not eligibility check)
    result = await review_service.report_review(
        db_session, principal=reporter, review_id=rid, reason_code="spam", ctx=CTX
    )
    assert result["status"] == "reported"

    # After flagging the review must STILL be in the aggregate (ADR-0013 §flagged).
    post = await company_rating_facade.ratings_for(db_session, [partner.org_id])
    assert partner.org_id in post, "Flagged review must remain in aggregate"
    assert post[partner.org_id]["review_count"] == 1

    # Public list also still shows it.
    pub = await review_service.list_public_reviews(db_session, slug=slug)
    assert len(pub["items"]) == 1

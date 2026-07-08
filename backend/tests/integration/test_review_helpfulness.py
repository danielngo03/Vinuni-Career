"""Integration tests for review helpfulness voting and partner response (BATCH REVIEWS-2).

Covers:
- Authenticated user can vote a review helpful (idempotent).
- User can remove their helpful vote (idempotent).
- helpful_count increments/decrements correctly.
- Reviewer cannot vote on their own review.
- Guest/unauthenticated vote raises AuthRequiredError.
- Partner admin can add a public response to a review on their own org.
- Partner cannot respond to another org's review.
- partner_response is returned in the public list.
- my_vote is None for guests, True/False for authenticated callers.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.organization.domain.models import Organization
from app.modules.recruitment.application import access
from app.modules.reviews.application import review_moderation_service, review_service
from app.shared.exceptions import AuthRequiredError, ConflictError, ResourceNotFoundError
from app.shared.permissions import GUEST
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.integration.test_recruitment_offers import _setup_reviewed
from tests.org_utils import make_org_with_admin

_BODY = "A" * 60


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _org_slug(db, org_id: uuid.UUID) -> str:
    return (
        await db.execute(select(Organization.slug).where(Organization.id == org_id))
    ).scalar_one()


def _payload() -> dict:
    return {
        "title": "Great workplace for students",
        "body": _BODY,
        "pros": None,
        "cons": None,
        "is_anonymous": False,
        "overall": 5,
        "work_life_balance": 4,
        "culture_values": 5,
        "compensation": 3,
        "career_growth": 4,
    }


async def _create_published_review(db, *, student, partner, uni):
    """Submit + publish a review; returns the review dict."""
    slug = await _org_slug(db, partner.org_id)
    sub = await review_service.submit_review(
        db, principal=student, slug=slug, payload=_payload(), ctx=CTX
    )
    rid = uuid.UUID(sub["id"])
    return await review_moderation_service.publish_review(
        db, principal=uni, review_id=rid, ctx=CTX
    )


# --------------------------------------------------------------------------- #
# Helpful voting                                                               #
# --------------------------------------------------------------------------- #


async def test_vote_increments_count(db_session) -> None:
    partner, _su, student, _job, _app = await _setup_reviewed(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    pub = await _create_published_review(db_session, student=student, partner=partner, uni=uni)
    rid = uuid.UUID(pub["id"])

    _su2, voter = await make_student(db_session, prefix="voter")
    res = await review_service.vote_helpful(db_session, principal=voter, review_id=rid)
    assert res["helpful_count"] == 1
    assert res["my_vote"] is True


async def test_vote_is_idempotent(db_session) -> None:
    partner, _su, student, _job, _app = await _setup_reviewed(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    pub = await _create_published_review(db_session, student=student, partner=partner, uni=uni)
    rid = uuid.UUID(pub["id"])

    _su2, voter = await make_student(db_session, prefix="v2")
    await review_service.vote_helpful(db_session, principal=voter, review_id=rid)
    res = await review_service.vote_helpful(db_session, principal=voter, review_id=rid)
    assert res["helpful_count"] == 1  # Not double-counted.


async def test_remove_vote_decrements_count(db_session) -> None:
    partner, _su, student, _job, _app = await _setup_reviewed(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    pub = await _create_published_review(db_session, student=student, partner=partner, uni=uni)
    rid = uuid.UUID(pub["id"])

    _su2, voter = await make_student(db_session, prefix="v3")
    await review_service.vote_helpful(db_session, principal=voter, review_id=rid)
    res = await review_service.remove_helpful_vote(db_session, principal=voter, review_id=rid)
    assert res["helpful_count"] == 0
    assert res["my_vote"] is False


async def test_remove_vote_noop_if_not_voted(db_session) -> None:
    partner, _su, student, _job, _app = await _setup_reviewed(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    pub = await _create_published_review(db_session, student=student, partner=partner, uni=uni)
    rid = uuid.UUID(pub["id"])

    _su2, voter = await make_student(db_session, prefix="v4")
    res = await review_service.remove_helpful_vote(db_session, principal=voter, review_id=rid)
    assert res["helpful_count"] == 0  # No-op.


async def test_reviewer_cannot_vote_own_review(db_session) -> None:
    partner, _su, student, _job, _app = await _setup_reviewed(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    pub = await _create_published_review(db_session, student=student, partner=partner, uni=uni)
    rid = uuid.UUID(pub["id"])

    with pytest.raises(ConflictError):
        await review_service.vote_helpful(db_session, principal=student, review_id=rid)


async def test_guest_vote_raises_auth_error(db_session) -> None:
    partner, _su, student, _job, _app = await _setup_reviewed(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    pub = await _create_published_review(db_session, student=student, partner=partner, uni=uni)
    rid = uuid.UUID(pub["id"])

    with pytest.raises(AuthRequiredError):
        await review_service.vote_helpful(db_session, principal=GUEST, review_id=rid)


async def test_my_vote_in_public_list(db_session) -> None:
    partner, _su, student, _job, _app = await _setup_reviewed(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    pub = await _create_published_review(db_session, student=student, partner=partner, uni=uni)
    rid = uuid.UUID(pub["id"])
    slug = await _org_slug(db_session, partner.org_id)

    _su2, voter = await make_student(db_session, prefix="v5")
    await review_service.vote_helpful(db_session, principal=voter, review_id=rid)

    # Voter sees my_vote=True.
    result_voter = await review_service.list_public_reviews(
        db_session, slug=slug, principal=voter
    )
    item = next(r for r in result_voter["items"] if r["id"] == str(rid))
    assert item["helpful_count"] == 1
    assert item["my_vote"] is True

    # Non-voter sees my_vote=False.
    _su3, other = await make_student(db_session, prefix="v6")
    result_other = await review_service.list_public_reviews(
        db_session, slug=slug, principal=other
    )
    item2 = next(r for r in result_other["items"] if r["id"] == str(rid))
    assert item2["my_vote"] is False

    # Guest sees my_vote=None.
    result_guest = await review_service.list_public_reviews(
        db_session, slug=slug, principal=GUEST
    )
    item3 = next(r for r in result_guest["items"] if r["id"] == str(rid))
    assert item3["my_vote"] is None


# --------------------------------------------------------------------------- #
# Partner response                                                             #
# --------------------------------------------------------------------------- #


async def test_partner_can_add_response(db_session) -> None:
    partner, _su, student, _job, _app = await _setup_reviewed(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    pub = await _create_published_review(db_session, student=student, partner=partner, uni=uni)
    rid = uuid.UUID(pub["id"])
    slug = await _org_slug(db_session, partner.org_id)

    res = await review_service.add_partner_response(
        db_session, principal=partner, review_id=rid,
        response_text="Thank you for your feedback!", ctx=CTX,
    )
    assert res["status"] == "ok"

    # Appears in public list.
    data = await review_service.list_public_reviews(db_session, slug=slug)
    item = next(r for r in data["items"] if r["id"] == str(rid))
    assert item["partner_response"] == "Thank you for your feedback!"
    assert item["partner_response_at"] is not None


async def test_partner_cannot_respond_to_other_org_review(db_session) -> None:
    partner, _su, student, _job, _app = await _setup_reviewed(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    pub = await _create_published_review(db_session, student=student, partner=partner, uni=uni)
    rid = uuid.UUID(pub["id"])

    # Different partner org cannot respond.
    _pu2, _org2, other_partner = await make_org_with_admin(
        db_session, admin_email="other-partner@test.invalid", display_name="Other Corp"
    )
    with pytest.raises(ResourceNotFoundError):
        await review_service.add_partner_response(
            db_session, principal=other_partner, review_id=rid,
            response_text="I should not be able to respond to this.",
            ctx=CTX,
        )

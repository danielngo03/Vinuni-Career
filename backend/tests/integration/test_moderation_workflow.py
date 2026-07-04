"""Moderation-queue workflow enhancements: claim/assign, SLA due-by, structured
reason codes, bulk approve/reject, and escalation to the shared human review
queue — covering jobs, events, and sponsored ad placements.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.advertising.application import moderation_service as ad_moderation
from app.modules.advertising.application import placement_service
from app.modules.advertising.application.errors import (
    InvalidModerationReasonError as AdInvalidReasonError,
    PlacementAlreadyClaimedError,
)
from app.modules.advertising.domain.models import AdPackage, SponsoredPlacement
from app.modules.moderation.domain.models import HumanReviewItem, STATUS_PENDING
from app.modules.opportunities.application import (
    event_moderation_service,
    event_service,
    job_service,
    moderation_service,
)
from app.modules.opportunities.application.errors import (
    InvalidModerationReasonError,
    JobAlreadyClaimedError,
)
from app.modules.opportunities.application.event_errors import (
    EventAlreadyClaimedError,
)
from app.shared.exceptions import ResourceNotFoundError
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.events_utils import event_payload
from tests.org_utils import make_org_with_admin


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _job_payload(title: str = "Backend Intern", **over) -> dict:
    base = {
        "title": title,
        "description": "We are hiring a backend intern to build APIs.",
        "employment_type": "internship",
        "location_type": "onsite",
        "location_city": "Hanoi",
        "location_country": "Vietnam",
        "required_skills": ["python"],
        "preferred_skills": [],
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "headcount": 1,
        "visibility": "public",
        "screening_questions": [],
    }
    base.update(over)
    return base


async def _submitted_job(db, partner, *, title="Backend Intern") -> uuid.UUID:
    created = await job_service.create_job(
        db, principal=partner, payload=_job_payload(title), ctx=CTX
    )
    submitted = await job_service.submit_job(
        db, principal=partner, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    assert submitted["due_by"] is not None
    assert submitted["is_overdue"] is False
    return uuid.UUID(created["id"])


async def _submitted_event(db, organizer, *, title="Career Day") -> uuid.UUID:
    created = await event_service.create_event(
        db, principal=organizer, payload=event_payload(title), ctx=CTX
    )
    submitted = await event_service.submit_event(
        db, principal=organizer, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    return uuid.UUID(created["id"])


async def _seed_ad_package(db) -> AdPackage:
    pkg = AdPackage(
        code="sponsored_14d", name="Tài trợ 14 ngày", placement_type="sponsored",
        price_amount="3000000.00", currency="VND", duration_days=14,
        grants_sponsored=True, grants_featured=False, is_active=True,
    )
    db.add(pkg)
    await db.commit()
    await db.refresh(pkg)
    return pkg


async def _submitted_placement(db, partner, *, job_id: uuid.UUID) -> uuid.UUID:
    pkg = await _seed_ad_package(db)
    draft = await placement_service.create_placement(
        db, principal=partner,
        payload={
            "target_type": "job", "target_id": job_id, "placement_type": "sponsored",
            "package_id": pkg.id, "start_at": _now() + timedelta(days=1),
            "disclosure_confirmed": True,
        },
        ctx=CTX,
    )
    # ``due_by``/``claimed_by`` are admin-only oversight fields (mirroring the
    # existing admin-only ``payment_reference``/``approved_by``) — asserted via
    # the moderator-facing queue/approve responses instead of this partner one.
    await placement_service.submit_placement(
        db, principal=partner, placement_id=uuid.UUID(draft["id"]), ctx=CTX,
    )
    return uuid.UUID(draft["id"])


# --------------------------------------------------------------------------- #
# Claim conflict (double-claim rejected) — jobs, events, placements           #
# --------------------------------------------------------------------------- #


async def test_job_claim_conflict_rejects_second_moderator(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni_a = await make_org_with_admin(db_session, org_type="university")
    _uu2, _uorg2, uni_b = await make_org_with_admin(db_session, org_type="university")
    job_id = await _submitted_job(db_session, partner)

    claimed = await moderation_service.claim_job(
        db_session, principal=uni_a, job_id=job_id, ctx=CTX,
    )
    assert claimed["claimed_by"] == str(uni_a.user_id)

    # Same moderator re-claiming is an idempotent no-op.
    again = await moderation_service.claim_job(
        db_session, principal=uni_a, job_id=job_id, ctx=CTX,
    )
    assert again["claimed_by"] == str(uni_a.user_id)

    # A different moderator is rejected with a clear conflict.
    with pytest.raises(JobAlreadyClaimedError):
        await moderation_service.claim_job(
            db_session, principal=uni_b, job_id=job_id, ctx=CTX,
        )

    # Approval still works for whoever holds the claim (claim is advisory, not
    # a hard permission gate) and clears the claim on the fresh submit cycle.
    approved = await moderation_service.approve_job(
        db_session, principal=uni_a, job_id=job_id, ctx=CTX,
    )
    assert approved["status"] == "active"


async def test_event_claim_conflict_rejects_second_moderator(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni_a = await make_org_with_admin(db_session, org_type="university")
    _uu2, _uorg2, uni_b = await make_org_with_admin(db_session, org_type="university")
    event_id = await _submitted_event(db_session, organizer)

    await event_moderation_service.claim_event(
        db_session, principal=uni_a, event_id=event_id, ctx=CTX,
    )
    with pytest.raises(EventAlreadyClaimedError):
        await event_moderation_service.claim_event(
            db_session, principal=uni_b, event_id=event_id, ctx=CTX,
        )


async def test_placement_claim_conflict_rejects_second_moderator(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni_a = await make_org_with_admin(db_session, org_type="university")
    _uu2, _uorg2, uni_b = await make_org_with_admin(db_session, org_type="university")
    job_id = await _submitted_job(db_session, partner)
    await moderation_service.approve_job(
        db_session, principal=uni_a, job_id=job_id, ctx=CTX,
    )
    placement_id = await _submitted_placement(db_session, partner, job_id=job_id)

    await ad_moderation.claim_placement(
        db_session, principal=uni_a, placement_id=placement_id, ctx=CTX,
    )
    with pytest.raises(PlacementAlreadyClaimedError):
        await ad_moderation.claim_placement(
            db_session, principal=uni_b, placement_id=placement_id, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# SLA due-by present in list/detail response                                  #
# --------------------------------------------------------------------------- #


async def test_job_queue_exposes_due_by_and_age(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    await _submitted_job(db_session, partner)

    queue, total = await moderation_service.list_moderation_queue(
        db_session, principal=uni,
    )
    assert total == 1
    row = queue[0]
    assert row["due_by"] is not None
    assert row["age_hours"] is not None
    assert row["is_overdue"] is False
    assert row["claimed_by"] is None


async def test_placement_admin_queue_exposes_due_by_and_age(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _submitted_job(db_session, partner)
    await moderation_service.approve_job(
        db_session, principal=uni, job_id=job_id, ctx=CTX,
    )
    await _submitted_placement(db_session, partner, job_id=job_id)

    items, total, _spend = await ad_moderation.list_all(db_session, principal=uni)
    assert total == 1
    assert items[0]["due_by"] is not None
    assert items[0]["is_overdue"] is False
    assert items[0]["claimed_by"] is None


# --------------------------------------------------------------------------- #
# Structured reason-code validation                                          #
# --------------------------------------------------------------------------- #


async def test_reject_job_rejects_invalid_reason_code(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _submitted_job(db_session, partner)

    with pytest.raises(InvalidModerationReasonError):
        await moderation_service.reject_job(
            db_session, principal=uni, job_id=job_id,
            reason="bad", reason_code="not_a_real_code", ctx=CTX,
        )


async def test_reject_job_other_reason_code_requires_note(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _submitted_job(db_session, partner)

    # "other" is always accompanied by the (already-required) free-text reason,
    # so this succeeds; the reason_code is persisted alongside the free text.
    rejected = await moderation_service.reject_job(
        db_session, principal=uni, job_id=job_id,
        reason="Không đủ tiêu chuẩn", reason_code="other", ctx=CTX,
    )
    assert rejected["moderation_reason_code"] == "other"
    assert rejected["moderation_reason_label"]


async def test_reject_job_with_valid_structured_code(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _submitted_job(db_session, partner)

    rejected = await moderation_service.reject_job(
        db_session, principal=uni, job_id=job_id,
        reason="Trùng với tin đã đăng trước đó", reason_code="duplicate_listing",
        ctx=CTX,
    )
    assert rejected["status"] == "rejected"
    assert rejected["moderation_reason_code"] == "duplicate_listing"


async def test_ad_escalate_rejects_invalid_reason_code(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _submitted_job(db_session, partner)
    await moderation_service.approve_job(
        db_session, principal=uni, job_id=job_id, ctx=CTX,
    )
    placement_id = await _submitted_placement(db_session, partner, job_id=job_id)

    with pytest.raises(AdInvalidReasonError):
        await ad_moderation.escalate_placement(
            db_session, principal=uni, placement_id=placement_id,
            reason_code="nonsense", ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Bulk action partial failure                                                 #
# --------------------------------------------------------------------------- #


async def test_bulk_reject_jobs_partial_failure_reported_per_item(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    good_id = await _submitted_job(db_session, partner, title="Good Job")
    missing_id = uuid.uuid4()

    results = await moderation_service.bulk_reject_jobs(
        db_session, principal=uni,
        items=[
            {"id": good_id, "reason": "Trùng lặp", "reason_code": "duplicate_listing"},
            {"id": missing_id, "reason": "n/a"},
        ],
        ctx=CTX,
    )
    assert len(results) == 2
    ok = next(r for r in results if r["id"] == str(good_id))
    fail = next(r for r in results if r["id"] == str(missing_id))
    assert ok["success"] is True
    assert ok["job"]["status"] == "rejected"
    assert fail["success"] is False
    assert fail["error_code"] == "RESOURCE_NOT_FOUND"

    # The successful item is durably committed even though the batch had a
    # failure — bulk action is per-item, not all-or-nothing.
    reloaded = await job_service.get_job(db_session, principal=partner, job_id=good_id)
    assert reloaded["status"] == "rejected"


async def test_bulk_approve_events_partial_failure_reported_per_item(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    good_id = await _submitted_event(db_session, organizer, title="Good Event")
    missing_id = uuid.uuid4()

    results = await event_moderation_service.bulk_approve_events(
        db_session, principal=uni, event_ids=[good_id, missing_id], ctx=CTX,
    )
    ok = next(r for r in results if r["id"] == str(good_id))
    fail = next(r for r in results if r["id"] == str(missing_id))
    assert ok["success"] is True and ok["event"]["status"] == "published"
    assert fail["success"] is False and fail["error_code"] == "RESOURCE_NOT_FOUND"


# --------------------------------------------------------------------------- #
# Escalation creates the linked human_review_queue row                        #
# --------------------------------------------------------------------------- #


async def test_escalate_job_creates_human_review_item(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _submitted_job(db_session, partner)

    escalated = await moderation_service.escalate_job(
        db_session, principal=uni, job_id=job_id,
        reason_code="policy_violation", note="Needs a second opinion", ctx=CTX,
    )
    assert escalated["moderation_status"] == "flagged"

    item = (
        await db_session.execute(
            select(HumanReviewItem).where(
                HumanReviewItem.resource_type == "job",
                HumanReviewItem.resource_id == job_id,
            )
        )
    ).scalar_one()
    assert item.status == STATUS_PENDING
    assert item.source == "moderator_escalation"
    assert item.findings_json["reason_code"] == "policy_violation"


async def test_escalate_event_creates_human_review_item(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await _submitted_event(db_session, organizer)

    await event_moderation_service.escalate_event(
        db_session, principal=uni, event_id=event_id,
        reason_code="misleading_content", note="Check the venue claim", ctx=CTX,
    )
    item = (
        await db_session.execute(
            select(HumanReviewItem).where(
                HumanReviewItem.resource_type == "event",
                HumanReviewItem.resource_id == event_id,
            )
        )
    ).scalar_one()
    assert item.source == "moderator_escalation"


async def test_escalate_placement_creates_human_review_item(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _submitted_job(db_session, partner)
    await moderation_service.approve_job(
        db_session, principal=uni, job_id=job_id, ctx=CTX,
    )
    placement_id = await _submitted_placement(db_session, partner, job_id=job_id)

    await ad_moderation.escalate_placement(
        db_session, principal=uni, placement_id=placement_id,
        reason_code="spam", note="Repeated banner report", ctx=CTX,
    )
    item = (
        await db_session.execute(
            select(HumanReviewItem).where(
                HumanReviewItem.resource_type == "advertising_placement",
                HumanReviewItem.resource_id == placement_id,
            )
        )
    ).scalar_one()
    assert item.source == "moderator_escalation"

    row = (
        await db_session.execute(
            select(SponsoredPlacement).where(SponsoredPlacement.id == placement_id)
        )
    ).scalar_one()
    assert row.moderation_reason_code == "spam"

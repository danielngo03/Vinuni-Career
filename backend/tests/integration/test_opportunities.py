"""Opportunities (jobs) service tests.

Covers: RBAC on create, tenant isolation, public-visibility filtering + 404
enumeration hiding, lifecycle transitions + illegal-transition rejection,
university-moderation gate (partner admin -> 403), edit-lock after publish,
optimistic version conflict, audit-on-every-transition, outbox notification on
approve/reject, public-count = visible-only, and cursor pagination.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.opportunities.application import job_service, moderation_service
from app.modules.opportunities.application.errors import (
    IllegalJobTransitionError,
    JobNotEditableError,
    JobQualityCheckFailedError,
    JobVersionConflictError,
)
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.models import AuditLog
from app.shared.permissions import GUEST
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin


def _payload(title: str = "Backend Intern", **over) -> dict:
    base = {
        "title": title,
        "description": "We are hiring a backend intern to build APIs.",
        "requirements": None,
        "benefits": None,
        "employment_type": "internship",
        "location_type": "onsite",
        "location_city": "Hanoi",
        "location_country": "Vietnam",
        "required_skills": ["python", "fastapi"],
        "preferred_skills": [],
        "experience_min_years": None,
        "experience_max_years": None,
        "degree_required": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "headcount": 1,
        "application_deadline": None,
        "visibility": "public",
        "screening_questions": [],
    }
    base.update(over)
    return base


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _publish(db, partner_principal, uni_principal, *, title="Live Job", **over):
    created = await job_service.create_job(
        db, principal=partner_principal, payload=_payload(title, **over), ctx=CTX
    )
    await job_service.submit_job(
        db, principal=partner_principal, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    await moderation_service.approve_job(
        db, principal=uni_principal, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    return uuid.UUID(created["id"])


# --------------------------------------------------------------------------- #
# RBAC on create                                                             #
# --------------------------------------------------------------------------- #


async def test_create_requires_jobs_create_permission(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(db_session)
    _m_u, _m, member = await add_member(
        db_session, org=org, permissions=[("members", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await job_service.create_job(
            db_session, principal=member, payload=_payload(), ctx=CTX
        )


async def test_member_with_jobs_create_can_create(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(db_session)
    _m_u, _m, member = await add_member(
        db_session, org=org, permissions=[("jobs", "create"), ("jobs", "read")]
    )
    job = await job_service.create_job(
        db_session, principal=member, payload=_payload(), ctx=CTX
    )
    assert job["status"] == "draft"
    assert job["moderation_status"] == "pending"
    assert job["status_label"]  # localized, never raw-only


async def test_job_location_preserves_province_and_ward(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    job = await job_service.create_job(
        db_session,
        principal=admin,
        payload=_payload(
            locations=[
                {
                    "type": "onsite",
                    "province_code": "HN",
                    "ward_code": "00001",
                    "ward_name": "Phường Hoàn Kiếm",
                    "city": "Hà Nội",
                    "country": "Vietnam",
                }
            ]
        ),
        ctx=CTX,
    )
    location = job["locations"][0]
    assert location["province_code"] == "HN"
    assert location["ward_code"] == "00001"
    assert location["ward_name"] == "Phường Hoàn Kiếm"
    assert job["location_city"] == "Hà Nội"


async def test_public_list_filters_by_ward_code(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    await _publish(
        db_session,
        admin,
        uni,
        title="Hoan Kiem Internship",
        locations=[
            {
                "type": "onsite",
                "province_code": "HN",
                "ward_code": "00001",
                "ward_name": "Phường Hoàn Kiếm",
                "city": "Hà Nội",
                "country": "Vietnam",
            }
        ],
    )
    await _publish(
        db_session,
        admin,
        uni,
        title="Tay Ho Internship",
        locations=[
            {
                "type": "onsite",
                "province_code": "HN",
                "ward_code": "00002",
                "ward_name": "Phường Tây Hồ",
                "city": "Hà Nội",
                "country": "Vietnam",
            }
        ],
    )

    items, _next, _limit, total = await job_service.list_public_jobs(
        db_session, principal=GUEST, province_code="HN", ward_code="00001"
    )

    assert total == 1
    assert items[0]["title"] == "Hoan Kiem Internship"


# --------------------------------------------------------------------------- #
# Tenant isolation                                                           #
# --------------------------------------------------------------------------- #


async def test_partner_sees_only_own_org_jobs(db_session) -> None:
    _ua, org_a, admin_a = await make_org_with_admin(db_session, display_name="Org A")
    _ub, _org_b, admin_b = await make_org_with_admin(db_session, display_name="Org B")
    job_a = await job_service.create_job(
        db_session, principal=admin_a, payload=_payload("A job"), ctx=CTX
    )

    items_a, _, _ = await job_service.list_my_jobs(db_session, principal=admin_a)
    items_b, _, _ = await job_service.list_my_jobs(db_session, principal=admin_b)
    assert [i["id"] for i in items_a] == [job_a["id"]]
    assert items_b == []

    # Cross-org detail access is indistinguishable from missing -> 404.
    with pytest.raises(ResourceNotFoundError):
        await job_service.get_job(db_session, principal=admin_b, job_id=uuid.UUID(job_a["id"]))


# --------------------------------------------------------------------------- #
# Public visibility + enumeration hiding                                     #
# --------------------------------------------------------------------------- #


async def test_guest_sees_only_published_jobs(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    draft = await job_service.create_job(
        db_session, principal=admin, payload=_payload("Draft Job"), ctx=CTX
    )
    live_id = await _publish(db_session, admin, uni, title="Published Job")

    # Guest list shows only the published job; count reflects visible-only.
    items, _next, _limit, total = await job_service.list_public_jobs(
        db_session, principal=GUEST
    )
    assert total == 1
    assert [i["id"] for i in items] == [str(live_id)]

    # Public detail works for the published job, leaks no moderation fields.
    detail = await job_service.get_job(db_session, principal=GUEST, job_id=live_id)
    assert "moderation_note" not in detail
    assert "moderation_status" not in detail

    # Draft is hidden from guests -> 404 (enumeration hiding).
    with pytest.raises(ResourceNotFoundError):
        await job_service.get_job(db_session, principal=GUEST, job_id=uuid.UUID(draft["id"]))


# --------------------------------------------------------------------------- #
# Lifecycle transitions + illegal transitions                               #
# --------------------------------------------------------------------------- #


async def test_submit_transition_and_illegal_resubmit(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    submitted = await job_service.submit_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
    )
    assert submitted["status"] == "pending_review"
    assert submitted["submitted_at"] is not None
    # Already pending_review -> submit again is illegal.
    with pytest.raises(IllegalJobTransitionError):
        await job_service.submit_job(
            db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
        )


async def test_close_draft_is_illegal(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    with pytest.raises(IllegalJobTransitionError):
        await job_service.close_job(
            db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
        )


async def test_close_and_reopen_active_job(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish(db_session, admin, uni)

    closed = await job_service.close_job(
        db_session, principal=admin, job_id=job_id, ctx=CTX
    )
    assert closed["status"] == "closed"
    # Closed jobs are not publicly visible.
    with pytest.raises(ResourceNotFoundError):
        await job_service.get_job(db_session, principal=GUEST, job_id=job_id)

    reopened = await job_service.reopen_job(
        db_session, principal=admin, job_id=job_id, ctx=CTX
    )
    assert reopened["status"] == "active"
    detail = await job_service.get_job(db_session, principal=GUEST, job_id=job_id)
    assert detail["id"] == str(job_id)


# --------------------------------------------------------------------------- #
# Moderation gate + approve/reject                                           #
# --------------------------------------------------------------------------- #


async def test_partner_admin_cannot_moderate(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)  # partner *:*
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    await job_service.submit_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
    )
    # Partner admin holds *:* but org_type != university -> 403.
    with pytest.raises(PermissionDeniedError):
        await moderation_service.approve_job(
            db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
        )
    with pytest.raises(PermissionDeniedError):
        await moderation_service.list_moderation_queue(db_session, principal=admin)


async def test_university_moderation_queue_and_approve(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    await job_service.submit_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
    )
    queue, total = await moderation_service.list_moderation_queue(
        db_session, principal=uni
    )
    assert total == 1 and queue[0]["id"] == job["id"]

    approved = await moderation_service.approve_job(
        db_session, principal=uni, job_id=uuid.UUID(job["id"]), ctx=CTX
    )
    assert approved["status"] == "active"

    # Outbox notification queued to the posting partner.
    outbox = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.template_key == "job.approved"
            )
        )
    ).scalars().all()
    assert len(outbox) == 1


async def test_reject_notifies_and_sets_rejected(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    await job_service.submit_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
    )
    rejected = await moderation_service.reject_job(
        db_session, principal=uni, job_id=uuid.UUID(job["id"]),
        reason="Mô tả công việc chưa rõ ràng.", ctx=CTX,
    )
    assert rejected["status"] == "rejected"

    outbox = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.template_key == "job.rejected"
            )
        )
    ).scalars().all()
    assert len(outbox) == 1

    # A rejected job is editable again, then resubmittable.
    edited = await job_service.update_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]),
        payload={"title": "Backend Intern (revised)"}, ctx=CTX,
    )
    assert edited["title"] == "Backend Intern (revised)"
    resubmitted = await job_service.submit_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
    )
    assert resubmitted["status"] == "pending_review"


# --------------------------------------------------------------------------- #
# Edit lock + optimistic concurrency                                         #
# --------------------------------------------------------------------------- #


async def test_closed_job_is_edit_locked(db_session) -> None:
    """A closed (not merely active) job stays fully edit-locked (B-552)."""
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish(db_session, admin, uni)
    await job_service.close_job(db_session, principal=admin, job_id=job_id, ctx=CTX)
    with pytest.raises(JobNotEditableError):
        await job_service.update_job(
            db_session, principal=admin, job_id=job_id,
            payload={"title": "New title"}, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Post-publication amendment policy (B-552)                                 #
# --------------------------------------------------------------------------- #


async def test_free_amend_field_stays_active_and_public(db_session) -> None:
    """Deadline/headcount/visibility/benefits edit freely without re-moderation."""
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish(db_session, admin, uni)

    edited = await job_service.update_job(
        db_session, principal=admin, job_id=job_id,
        payload={"headcount": 5, "benefits": "Free lunch, health insurance."},
        ctx=CTX,
    )
    assert edited["status"] == "active"
    assert edited["moderation_status"] == "approved"
    assert edited["headcount"] == 5

    # Still publicly visible — amendment did not unpublish it.
    detail = await job_service.get_job(db_session, principal=GUEST, job_id=job_id)
    assert detail["id"] == str(job_id)


async def test_content_amend_on_active_job_requires_remoderation(db_session) -> None:
    """Title/description/salary/etc. edits on a live job re-enter moderation."""
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish(db_session, admin, uni)

    edited = await job_service.update_job(
        db_session, principal=admin, job_id=job_id,
        payload={"title": "Backend Intern (Revised)"}, ctx=CTX,
    )
    assert edited["status"] == "pending_review"
    assert edited["moderation_status"] == "pending"

    # Unpublished while re-pending — a guest can no longer see it.
    with pytest.raises(ResourceNotFoundError):
        await job_service.get_job(db_session, principal=GUEST, job_id=job_id)

    # Re-approve and it becomes visible again with the amended title.
    approved = await moderation_service.approve_job(
        db_session, principal=uni, job_id=job_id, ctx=CTX
    )
    assert approved["status"] == "active"
    detail = await job_service.get_job(db_session, principal=GUEST, job_id=job_id)
    assert detail["title"] == "Backend Intern (Revised)"


async def test_screening_questions_locked_after_publish(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish(db_session, admin, uni)

    with pytest.raises(JobNotEditableError):
        await job_service.update_job(
            db_session, principal=admin, job_id=job_id,
            payload={"screening_questions": [
                {"question": "Are you eligible to work in Vietnam?", "q_type": "yes_no"}
            ]},
            ctx=CTX,
        )


async def test_amendment_audit_records_before_after_diff(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish(db_session, admin, uni)

    before_count = await _audit_count(db_session, "job.updated")
    await job_service.update_job(
        db_session, principal=admin, job_id=job_id,
        payload={"headcount": 9}, ctx=CTX,
    )
    after_count = await _audit_count(db_session, "job.updated")
    assert after_count == before_count + 1

    row = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == "job.updated", AuditLog.resource_id == job_id)
            .order_by(AuditLog.occurred_at.desc())
        )
    ).scalars().first()
    assert row is not None
    assert row.after_snapshot["diff"]["before"]["headcount"] == 1
    assert row.after_snapshot["diff"]["after"]["headcount"] == 9


async def test_optimistic_version_conflict(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    with pytest.raises(JobVersionConflictError):
        await job_service.update_job(
            db_session, principal=admin, job_id=uuid.UUID(job["id"]),
            payload={"title": "Race", "version": 999}, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Audit on every transition                                                  #
# --------------------------------------------------------------------------- #


async def test_audit_written_on_every_transition(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    assert await _audit_count(db_session, "job.created") == 1
    await job_service.submit_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
    )
    assert await _audit_count(db_session, "job.submit") == 1
    await moderation_service.approve_job(
        db_session, principal=uni, job_id=uuid.UUID(job["id"]), ctx=CTX
    )
    assert await _audit_count(db_session, "job.approved") == 1
    await job_service.close_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
    )
    assert await _audit_count(db_session, "job.close") == 1


# --------------------------------------------------------------------------- #
# Moderator read access + approve-empty-body fixes (Phase 1e)                 #
# --------------------------------------------------------------------------- #


async def test_university_moderator_can_view_pending_job_detail(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    await job_service.submit_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
    )
    # University moderator sees the FULL detail (incl. moderation fields) while
    # the job is pending_review.
    detail = await job_service.get_job(
        db_session, principal=uni, job_id=uuid.UUID(job["id"])
    )
    assert detail["status"] == "pending_review"
    assert "moderation_status" in detail
    assert detail["screening_questions"] == []

    # A different (non-university) partner still gets 404 (tenant/enumeration).
    _ob_u, _ob, other_partner = await make_org_with_admin(
        db_session, display_name="Other Co"
    )
    with pytest.raises(ResourceNotFoundError):
        await job_service.get_job(
            db_session, principal=other_partner, job_id=uuid.UUID(job["id"])
        )


def test_approve_request_accepts_empty_body() -> None:
    from app.modules.opportunities.api.schemas import (
        JobApproveRequest,
        JobModerationRejectRequest,
    )

    # Approve must validate with no/empty body (no 422).
    assert JobApproveRequest().version is None
    assert JobApproveRequest.model_validate({}).note is None
    # Reject still requires a reason.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JobModerationRejectRequest.model_validate({})


# --------------------------------------------------------------------------- #
# Pagination                                                                 #
# --------------------------------------------------------------------------- #


async def test_public_list_pagination(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    for i in range(3):
        await _publish(db_session, admin, uni, title=f"Job {i}")

    page1, cursor1, limit1, total = await job_service.list_public_jobs(
        db_session, principal=GUEST, limit=2
    )
    assert total == 3 and limit1 == 2 and len(page1) == 2 and cursor1 is not None
    page2, cursor2, _limit2, _total2 = await job_service.list_public_jobs(
        db_session, principal=GUEST, limit=2, cursor=cursor1
    )
    assert len(page2) == 1 and cursor2 is None
    ids = {j["id"] for j in page1} | {j["id"] for j in page2}
    assert len(ids) == 3


# --------------------------------------------------------------------------- #
# Job duplication                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_duplicate_job_creates_draft_copy(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    source = await job_service.create_job(
        db_session,
        principal=admin,
        payload=_payload(
            "Senior Python Dev",
            screening_questions=[
                {"question": "GitHub?", "q_type": "text", "is_required": True, "sort_order": 0}
            ],
        ),
        ctx=CTX,
    )
    source_id = uuid.UUID(source["id"])

    copy = await job_service.duplicate_job(
        db_session, principal=admin, job_id=source_id, ctx=CTX, locale="vi"
    )

    assert copy["id"] != source["id"]
    assert "(Sao chép)" in copy["title"]
    assert copy["status"] == "draft"
    assert copy["moderation_status"] == "pending"
    assert copy["slug"] != source["slug"]
    assert copy["description"] == source["description"]
    assert len(copy["screening_questions"]) == 1
    assert copy["screening_questions"][0]["question"] == "GitHub?"


@pytest.mark.asyncio
async def test_duplicate_job_cross_org_raises_404(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _u2, _org2, other = await make_org_with_admin(db_session, display_name="Other")
    source = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    with pytest.raises(ResourceNotFoundError):
        await job_service.duplicate_job(
            db_session, principal=other, job_id=uuid.UUID(source["id"]), ctx=CTX
        )


@pytest.mark.asyncio
async def test_duplicate_job_slug_is_unique(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    source = await job_service.create_job(
        db_session, principal=admin, payload=_payload("Unique Slug Job"), ctx=CTX
    )
    copy1 = await job_service.duplicate_job(
        db_session, principal=admin, job_id=uuid.UUID(source["id"]), ctx=CTX
    )
    copy2 = await job_service.duplicate_job(
        db_session, principal=admin, job_id=uuid.UUID(source["id"]), ctx=CTX
    )
    assert copy1["slug"] != copy2["slug"]


@pytest.mark.asyncio
async def test_duplicate_from_live_published_job_starts_clean_draft(db_session) -> None:
    """Clone-from-performing-job (B-552): duplicating a live/active job never
    carries forward its moderation/publish state — the copy always starts as
    a fresh, unpublished, unmoderated draft."""
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    live_id = await _publish(db_session, admin, uni, title="Top Performing Role")

    copy = await job_service.duplicate_job(
        db_session, principal=admin, job_id=live_id, ctx=CTX
    )
    assert copy["status"] == "draft"
    assert copy["moderation_status"] == "pending"
    assert copy["published_at"] is None
    assert copy["approved_at"] is None
    assert copy["application_count"] == 0

    # Audited with a pointer back to the source job.
    row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "job.duplicated",
                AuditLog.resource_id == uuid.UUID(copy["id"]),
            )
        )
    ).scalars().first()
    assert row is not None
    assert row.after_snapshot["source_job_id"] == str(live_id)


# --------------------------------------------------------------------------- #
# JD quality-check gate (B-552)                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_submit_blocked_by_thin_placeholder_description(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    job = await job_service.create_job(
        db_session, principal=admin,
        payload=_payload("Backend Intern", description="test"),
        ctx=CTX,
    )
    with pytest.raises(JobQualityCheckFailedError) as exc_info:
        await job_service.submit_job(
            db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
        )
    issues = exc_info.value.details["issues"]
    assert any(
        i["field"] == "description" and i["severity"] == "blocking" for i in issues
    )
    # Never resolved to a raw enum-only response — every issue carries a message.
    assert all(i["message"] for i in issues)


@pytest.mark.asyncio
async def test_submit_blocked_by_disclosed_salary_without_values(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    job = await job_service.create_job(
        db_session, principal=admin,
        payload=_payload("Backend Intern", salary_is_disclosed=True),
        ctx=CTX,
    )
    with pytest.raises(JobQualityCheckFailedError) as exc_info:
        await job_service.submit_job(
            db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
        )
    issues = exc_info.value.details["issues"]
    assert any(i["field"] == "salary" and i["severity"] == "blocking" for i in issues)


@pytest.mark.asyncio
async def test_submit_allows_advisory_only_warnings(db_session) -> None:
    """A thin-but-real JD (no requirements, salary undisclosed, no experience
    bound) surfaces advisory warnings but is NOT blocked."""
    _u, _org, admin = await make_org_with_admin(db_session)
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    result = await job_service.submit_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), ctx=CTX
    )
    assert result["status"] == "pending_review"
    assert result["quality_check"]["passed"] is True
    assert any(i["severity"] == "advisory" for i in result["quality_check"]["issues"])


@pytest.mark.asyncio
async def test_quality_check_preview_matches_submit_gate(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    job = await job_service.create_job(
        db_session, principal=admin,
        payload=_payload("Backend Intern", description="test"),
        ctx=CTX,
    )
    preview = await job_service.check_jd_quality(
        db_session, principal=admin, job_id=uuid.UUID(job["id"])
    )
    assert preview["passed"] is False
    assert any(i["severity"] == "blocking" for i in preview["issues"])


# --------------------------------------------------------------------------- #
# Pre-publish preview (guest/student)                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_preview_as_guest_shows_public_projection_before_publish(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload("Draft Preview Job"), ctx=CTX
    )
    out = await job_service.preview_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), as_persona="guest",
    )
    assert out["as"] == "guest"
    assert out["would_be_visible"] is True
    # Owner-only fields never leak into the preview projection.
    assert "moderation_status" not in out["preview"]
    assert "moderation_note" not in out["preview"]
    assert "posted_by" not in out["preview"]
    assert out["preview"]["title"] == "Draft Preview Job"


@pytest.mark.asyncio
async def test_preview_hides_students_only_job_from_guest(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    job = await job_service.create_job(
        db_session, principal=admin,
        payload=_payload("Students Only Job", visibility="students_only"),
        ctx=CTX,
    )
    guest_view = await job_service.preview_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), as_persona="guest",
    )
    assert guest_view["would_be_visible"] is False
    assert guest_view["hidden_reason"] == "visibility_tier"

    student_view = await job_service.preview_job(
        db_session, principal=admin, job_id=uuid.UUID(job["id"]), as_persona="student",
    )
    assert student_view["would_be_visible"] is True


@pytest.mark.asyncio
async def test_preview_requires_jobs_read_permission(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    # A member who can create/submit but was never granted jobs:read.
    _m_u, _m, member_no_read = await add_member(
        db_session, org=org, permissions=[("jobs", "create"), ("jobs", "submit")]
    )
    with pytest.raises(PermissionDeniedError):
        await job_service.preview_job(
            db_session, principal=member_no_read, job_id=uuid.UUID(job["id"]),
            as_persona="guest",
        )


@pytest.mark.asyncio
async def test_preview_cross_org_raises_404(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _u2, _org2, other = await make_org_with_admin(db_session, display_name="Other")
    job = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    with pytest.raises(ResourceNotFoundError):
        await job_service.preview_job(
            db_session, principal=other, job_id=uuid.UUID(job["id"]), as_persona="guest",
        )


# --------------------------------------------------------------------------- #
# Weekly job digest sweep                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_weekly_digest_enqueues_for_students(db_session) -> None:
    from datetime import UTC, datetime

    from app.modules.opportunities.application.weekly_digest_service import (
        sweep_weekly_digest,
    )

    from tests.documents_utils import make_student

    _u1, _org1, partner = await make_org_with_admin(db_session)
    _u2, _org2, uni = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    student1, _p1 = await make_student(db_session, prefix="digest_s1")
    student2, _p2 = await make_student(db_session, prefix="digest_s2")

    await _publish(db_session, partner, uni, title="ML Engineer")
    await _publish(db_session, partner, uni, title="Backend Dev")

    now = datetime(2026, 6, 30, 8, 0, tzinfo=UTC)
    result = await sweep_weekly_digest(db_session, now=now)

    assert result["jobs_found"] >= 2
    assert result["digests_enqueued"] >= 2

    rows = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.template_key == "student.weekly_job_digest"
            )
        )
    ).scalars().all()
    recipient_ids = {r.recipient_id for r in rows}
    assert student1.id in recipient_ids
    assert student2.id in recipient_ids


@pytest.mark.asyncio
async def test_weekly_digest_deduplicates_same_week(db_session) -> None:
    from datetime import UTC, datetime

    from app.modules.opportunities.application.weekly_digest_service import (
        sweep_weekly_digest,
    )

    from tests.documents_utils import make_student

    _u1, _org1, partner = await make_org_with_admin(db_session, display_name="Dedup Corp")
    _u2, _org2, uni = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni2"
    )
    student, _ = await make_student(db_session, prefix="dedup_stu")
    await _publish(db_session, partner, uni, title="Dedup Job")

    now = datetime(2026, 6, 30, 9, 0, tzinfo=UTC)
    r1 = await sweep_weekly_digest(db_session, now=now)
    r2 = await sweep_weekly_digest(db_session, now=now)

    assert r1["digests_enqueued"] >= 1
    assert r2["digests_skipped"] >= 1
    assert r2["digests_enqueued"] == 0

    count = (
        await db_session.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(
                NotificationOutbox.template_key == "student.weekly_job_digest",
                NotificationOutbox.recipient_id == student.id,
            )
        )
    ).scalar_one()
    assert count == 1

"""AI human-review queue (B-579): surface AI/rule-FLAGGED jobs + events for a
human moderator's FINAL say (uphold -> reject, dismiss -> clear), grant-gated and
audited, with a user-safe flag reason label and no model internals.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.opportunities.application import (
    ai_review_queue_service,
    event_moderation_service,
    event_service,
    job_service,
    moderation_service,
)
from app.modules.opportunities.application.errors import IllegalJobTransitionError
from app.modules.opportunities.domain.models import Job
from app.shared.exceptions import ConflictError, PermissionDeniedError
from app.shared.models import AuditLog
from app.shared.permissions import Principal
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.events_utils import event_payload
from tests.org_utils import add_member, make_org_with_admin

# Any key/value carrying these substrings would be an AI-internals leak.
_FORBIDDEN = ("provider", "model", "confidence", "token", "latency", "prompt", "embedding")


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
    }
    base.update(over)
    return base


async def _flagged_job(db, partner, uni, *, title="Backend Intern") -> uuid.UUID:
    created = await job_service.create_job(
        db, principal=partner, payload=_job_payload(title), ctx=CTX
    )
    job_id = uuid.UUID(created["id"])
    await job_service.submit_job(db, principal=partner, job_id=job_id, ctx=CTX)
    escalated = await moderation_service.escalate_job(
        db, principal=uni, job_id=job_id,
        reason_code="policy_violation", note="Suspicious comp claim", ctx=CTX,
    )
    assert escalated["moderation_status"] == "flagged"
    return job_id


async def _flagged_event(db, organizer, uni, *, title="Career Day") -> uuid.UUID:
    created = await event_service.create_event(
        db, principal=organizer, payload=event_payload(title), ctx=CTX
    )
    event_id = uuid.UUID(created["id"])
    await event_service.submit_event(db, principal=organizer, event_id=event_id, ctx=CTX)
    await event_moderation_service.escalate_event(
        db, principal=uni, event_id=event_id,
        reason_code="misleading_content", note="Check the venue claim", ctx=CTX,
    )
    return event_id


async def _audit_count(db, action: str, resource_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.action == action, AuditLog.resource_id == resource_id
            )
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Read model: flagged items appear with user-safe reason labels + SLA         #
# --------------------------------------------------------------------------- #


async def test_flagged_job_and_event_appear_with_safe_reason_and_sla(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _flagged_job(db_session, partner, uni)
    event_id = await _flagged_event(db_session, partner, uni)

    items, counts = await ai_review_queue_service.list_queue(
        db_session, principal=uni, locale="en"
    )
    assert counts == {"job": 1, "event": 1, "total": 2}
    by_id = {it["id"]: it for it in items}
    job_item = by_id[str(job_id)]
    event_item = by_id[str(event_id)]

    # User-safe flag reason: code + readable label (NO raw model internals).
    assert job_item["item_type"] == "job"
    assert job_item["flag_reason_code"] == "policy_violation"
    assert job_item["flag_reason_label"] == "Policy violation"
    assert event_item["flag_reason_label"] == "Misleading content"

    # SLA/age surfaced from the flag anchor.
    assert job_item["flagged_at"] is not None
    assert job_item["due_by"] is not None
    assert job_item["age_hours"] is not None
    assert job_item["is_overdue"] is False
    assert job_item["human_acted"] is False


async def test_queue_item_never_leaks_model_internals(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    await _flagged_job(db_session, partner, uni)

    items, _counts = await ai_review_queue_service.list_queue(
        db_session, principal=uni, locale="en"
    )
    blob = " ".join(f"{k}={v}" for it in items for k, v in it.items()).lower()
    for needle in _FORBIDDEN:
        assert needle not in blob, f"leaked '{needle}' in queue item"


async def test_overdue_when_flag_older_than_sla(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _flagged_job(db_session, partner, uni)

    # Push the flag anchor well past the 4h AI-review SLA.
    job = (await db_session.execute(select(Job).where(Job.id == job_id))).scalar_one()
    job.moderation_flagged_at = datetime.now(tz=UTC) - timedelta(hours=10)
    await db_session.commit()

    items, _counts = await ai_review_queue_service.list_queue(
        db_session, principal=uni, locale="en"
    )
    assert items[0]["is_overdue"] is True


async def test_counts_badge_aggregate(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    await _flagged_job(db_session, partner, uni, title="One")
    await _flagged_job(db_session, partner, uni, title="Two")

    counts = await ai_review_queue_service.get_counts(db_session, principal=uni)
    assert counts["job"] == 2
    assert counts["total"] == 2


# --------------------------------------------------------------------------- #
# Human decision: uphold (reject) — reuses the reject transition + audits      #
# --------------------------------------------------------------------------- #


async def test_uphold_flag_rejects_job_and_audits(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _flagged_job(db_session, partner, uni)

    result = await ai_review_queue_service.uphold(
        db_session, principal=uni, item_type="job", item_id=job_id,
        reason="Confirmed policy violation after review", ctx=CTX, locale="en",
    )
    assert result["decision"] == "uphold"
    item = result["item"]
    assert item["status"] == "rejected"
    assert item["moderation_status"] == "rejected"

    # Flag resolved -> item leaves the queue.
    _items, counts = await ai_review_queue_service.list_queue(db_session, principal=uni)
    assert counts["total"] == 0

    # Both the flag-decision audit and the reused reject audit exist.
    assert await _audit_count(db_session, "job.flag_upheld", job_id) == 1
    assert await _audit_count(db_session, "job.rejected", job_id) == 1


async def test_uphold_event_rejects_and_audits(db_session):
    _u, _o, organizer = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await _flagged_event(db_session, organizer, uni)

    result = await ai_review_queue_service.uphold(
        db_session, principal=uni, item_type="event", item_id=event_id,
        reason="Venue claim is false", ctx=CTX, locale="en",
    )
    assert result["item"]["moderation_status"] == "rejected"
    assert await _audit_count(db_session, "event.flag_upheld", event_id) == 1
    assert await _audit_count(db_session, "event.rejected", event_id) == 1


# --------------------------------------------------------------------------- #
# Human decision: dismiss (clear the flag) — new flag-clear path + audits      #
# --------------------------------------------------------------------------- #


async def test_dismiss_flag_clears_and_returns_to_pending(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _flagged_job(db_session, partner, uni)

    result = await ai_review_queue_service.dismiss(
        db_session, principal=uni, item_type="job", item_id=job_id,
        reason="False positive — comp figures verified", ctx=CTX, locale="en",
    )
    assert result["decision"] == "dismiss"
    item = result["item"]
    # Status unchanged (still pending review); flag cleared back to pending.
    assert item["status"] == "pending_review"
    assert item["moderation_status"] == "pending"

    job = (await db_session.execute(select(Job).where(Job.id == job_id))).scalar_one()
    assert job.moderation_reason_code is None
    assert job.moderation_flagged_at is None

    _items, counts = await ai_review_queue_service.list_queue(db_session, principal=uni)
    assert counts["total"] == 0
    assert await _audit_count(db_session, "job.flag_cleared", job_id) == 1


async def test_dismiss_active_flagged_job_returns_to_approved(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    created = await job_service.create_job(
        db_session, principal=partner, payload=_job_payload("Live Role"), ctx=CTX
    )
    job_id = uuid.UUID(created["id"])
    await job_service.submit_job(db_session, principal=partner, job_id=job_id, ctx=CTX)
    await moderation_service.approve_job(db_session, principal=uni, job_id=job_id, ctx=CTX)
    # Flag a live/approved job (e.g. a post-publication rescan).
    await moderation_service.escalate_job(
        db_session, principal=uni, job_id=job_id, reason_code="spam", note="rescan",
        ctx=CTX,
    )

    result = await ai_review_queue_service.dismiss(
        db_session, principal=uni, item_type="job", item_id=job_id,
        reason="Not spam", ctx=CTX, locale="en",
    )
    assert result["item"]["status"] == "active"
    assert result["item"]["moderation_status"] == "approved"


async def test_dismiss_is_idempotent_when_not_flagged(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    created = await job_service.create_job(
        db_session, principal=partner, payload=_job_payload("Plain"), ctx=CTX
    )
    job_id = uuid.UUID(created["id"])
    await job_service.submit_job(db_session, principal=partner, job_id=job_id, ctx=CTX)

    # Never flagged -> dismiss is a no-op (no error, no audit row).
    result = await ai_review_queue_service.dismiss(
        db_session, principal=uni, item_type="job", item_id=job_id,
        reason="nothing to clear", ctx=CTX, locale="en",
    )
    assert result["item"]["moderation_status"] == "pending"
    assert await _audit_count(db_session, "job.flag_cleared", job_id) == 0


async def test_uphold_requires_flagged_item(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    created = await job_service.create_job(
        db_session, principal=partner, payload=_job_payload("NotFlagged"), ctx=CTX
    )
    job_id = uuid.UUID(created["id"])
    await job_service.submit_job(db_session, principal=partner, job_id=job_id, ctx=CTX)

    with pytest.raises(ConflictError):
        await ai_review_queue_service.uphold(
            db_session, principal=uni, item_type="job", item_id=job_id,
            reason="x", ctx=CTX,
        )


async def test_uphold_active_flagged_job_is_not_rejectable(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    created = await job_service.create_job(
        db_session, principal=partner, payload=_job_payload("Live"), ctx=CTX
    )
    job_id = uuid.UUID(created["id"])
    await job_service.submit_job(db_session, principal=partner, job_id=job_id, ctx=CTX)
    await moderation_service.approve_job(db_session, principal=uni, job_id=job_id, ctx=CTX)
    await moderation_service.escalate_job(
        db_session, principal=uni, job_id=job_id, reason_code="spam", ctx=CTX,
    )

    # An active job cannot be sent through the reject transition; the honest
    # error surfaces (dismiss or take it down via the normal lifecycle instead).
    with pytest.raises(IllegalJobTransitionError):
        await ai_review_queue_service.uphold(
            db_session, principal=uni, item_type="job", item_id=job_id,
            reason="take it down", ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# RBAC: grant-gated (granted allowed / ungranted denied / superadmin allowed) #
# --------------------------------------------------------------------------- #


async def test_partner_cannot_read_ai_review_queue(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await ai_review_queue_service.list_queue(db_session, principal=partner)


async def test_unauthenticated_denied(db_session):
    from app.shared.exceptions import AuthRequiredError

    guest = Principal(user_id=None, persona="guest", org_id=None)
    with pytest.raises(AuthRequiredError):
        await ai_review_queue_service.list_queue(db_session, principal=guest)


async def test_superadmin_sees_all_flagged(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    await _flagged_job(db_session, partner, uni)
    await _flagged_event(db_session, partner, uni)

    superadmin = Principal(
        user_id=uuid.uuid4(), persona="superadmin", org_id=None, is_superadmin=True
    )
    _items, counts = await ai_review_queue_service.list_queue(
        db_session, principal=superadmin, locale="en"
    )
    assert counts["total"] == 2


async def test_jobs_only_moderator_sees_jobs_not_events(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, uni_org, uni = await make_org_with_admin(db_session, org_type="university")
    # A university member granted ONLY jobs:moderate.
    _mu, _mem, jobs_only = await add_member(
        db_session, org=uni_org, permissions=[("jobs", "moderate")]
    )
    await _flagged_job(db_session, partner, uni)
    event_id = await _flagged_event(db_session, partner, uni)

    items, counts = await ai_review_queue_service.list_queue(
        db_session, principal=jobs_only, locale="en"
    )
    assert counts == {"job": 1, "event": 0, "total": 1}
    assert all(it["item_type"] == "job" for it in items)

    # And cannot act on an event they hold no grant for.
    with pytest.raises(PermissionDeniedError):
        await ai_review_queue_service.uphold(
            db_session, principal=jobs_only, item_type="event", item_id=event_id,
            reason="no grant", ctx=CTX,
        )


async def test_unknown_item_type_rejected(db_session):
    from app.shared.exceptions import ValidationFailedError

    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    with pytest.raises(ValidationFailedError):
        await ai_review_queue_service.dismiss(
            db_session, principal=uni, item_type="banner", item_id=uuid.uuid4(),
            reason="x", ctx=CTX,
        )

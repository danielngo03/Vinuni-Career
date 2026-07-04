"""Pipeline-stage SLA reminder sweep tests (ADR-0003 scheduler seam).

Covers: approaching (80%) then overdue (100%+) escalation, idempotency (no
duplicate notification for an already-notified level; a re-tick at the SAME
level enqueues nothing new), reviewer-scoped recipient (the user who moved the
candidate into the stage, never a broadcast to the whole org), fallback to the
job owner when the reviewer has left the org, and a no-op when ``sla_hours`` is
unset.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.modules.automation.scheduler import runner
from app.modules.notifications.application.dispatch_service import process_outbox
from app.modules.notifications.application.template_seed import ensure_default_templates
from app.modules.notifications.domain.models import Notification, NotificationOutbox
from app.modules.organization.domain.models import Membership
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    sla_reminder_service,
    stage_service,
)
from app.modules.recruitment.domain.models import CandidateStage, PipelineStage
from app.modules.documents.application import snapshot_service

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _setup_reviewed(db: AsyncSession):
    """Published job + applied + reviewed (candidate ACTIVE at stage 1)."""

    _pu, porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=partner, uni_principal=uni)

    su, student = await make_student(db, prefix="student")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(
        db, principal=partner, application_id=app_id, ctx=CTX
    )
    return porg, partner, job_id, app_id


async def _current_row(db, app_id) -> tuple[CandidateStage, PipelineStage]:
    active = await stage_service._active_stage(db, application_id=app_id)
    assert active is not None
    stage = (
        await db.execute(select(PipelineStage).where(PipelineStage.id == active.stage_id))
    ).scalar_one()
    return active, stage


async def _set_sla(db, app_id, *, sla_hours: int, entered_hours_ago: float = 0) -> None:
    cs, stage = await _current_row(db, app_id)
    stage.sla_hours = sla_hours
    cs.entered_at = _now() - timedelta(hours=entered_hours_ago)
    await db.commit()


async def _sla_outbox_count(db, cs_id) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.dedupe_key.like(f"pipeline.sla_reminder:{cs_id}:%"))
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_no_reminder_below_approaching_threshold(db_session) -> None:
    _org, _partner, _job, app_id = await _setup_reviewed(db_session)
    # 24h SLA, only 1h elapsed (~4%) -> nothing due.
    await _set_sla(db_session, app_id, sla_hours=24, entered_hours_ago=1)

    result = await sla_reminder_service.sweep_sla_reminders(db_session, now=_now())
    assert result["sla_reminders"] == 0


@pytest.mark.asyncio
async def test_approaching_then_overdue_escalation_is_idempotent(db_session) -> None:
    _org, partner, _job, app_id = await _setup_reviewed(db_session)
    # 24h SLA, 20h elapsed = 83% -> "approaching".
    await _set_sla(db_session, app_id, sla_hours=24, entered_hours_ago=20)
    cs, _stage = await _current_row(db_session, app_id)

    res1 = await sla_reminder_service.sweep_sla_reminders(db_session, now=_now())
    assert res1["sla_reminders"] == 1
    await db_session.refresh(cs)
    assert cs.sla_reminder_level == "approaching"
    assert cs.sla_reminder_sent_at is not None

    # Re-tick at the same elapsed ratio: no new notification (already at this level).
    res2 = await sla_reminder_service.sweep_sla_reminders(db_session, now=_now())
    assert res2["sla_reminders"] == 0
    assert await _sla_outbox_count(db_session, cs.id) == 1

    # Now push past 100% -> escalates to "overdue" (a NEW notification).
    await _set_sla(db_session, app_id, sla_hours=24, entered_hours_ago=25)
    res3 = await sla_reminder_service.sweep_sla_reminders(db_session, now=_now())
    assert res3["sla_reminders"] == 1
    await db_session.refresh(cs)
    assert cs.sla_reminder_level == "overdue"
    assert await _sla_outbox_count(db_session, cs.id) == 2

    # A further re-tick at "overdue" is a no-op.
    res4 = await sla_reminder_service.sweep_sla_reminders(db_session, now=_now())
    assert res4["sla_reminders"] == 0
    assert await _sla_outbox_count(db_session, cs.id) == 2


@pytest.mark.asyncio
async def test_recipient_is_reviewer_not_whole_org(db_session) -> None:
    """Only the reviewer who moved the candidate (``entered_by``) is notified —
    NOT every org member (department/ownership scoping, not a broadcast)."""

    _org, partner, _job, app_id = await _setup_reviewed(db_session)
    await _set_sla(db_session, app_id, sla_hours=10, entered_hours_ago=9)
    cs, _stage = await _current_row(db_session, app_id)
    assert cs.entered_by == partner.user_id

    await sla_reminder_service.sweep_sla_reminders(db_session, now=_now())

    rows = (
        await db_session.execute(select(NotificationOutbox).where(
            NotificationOutbox.dedupe_key.like(f"pipeline.sla_reminder:{cs.id}:%")
        ))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].recipient_id == partner.user_id

    feed = (
        await db_session.execute(
            select(Notification).where(Notification.recipient_id == partner.user_id)
        )
    ).scalars().all()
    assert any(n.notif_type == "recruitment.pipeline_sla_reminder" for n in feed)


@pytest.mark.asyncio
async def test_falls_back_to_job_owner_when_reviewer_inactive(db_session) -> None:
    """When ``entered_by`` (the reviewer) is no longer active, fall back to the
    job's owner (``jobs.posted_by``) — still never a broadcast to the whole org."""

    porg, _uu, uni = None, None, None
    _pu, porg, org_admin = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    poster_user, _membership, poster = await add_member(
        db_session, org=porg,
        permissions=[("jobs", "create"), ("jobs", "submit"), ("jobs", "update")],
    )
    job_id = await publish_job(
        db_session, partner_principal=poster, uni_principal=uni
    )
    su, student = await make_student(db_session, prefix="student")
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    # ``org_admin`` (a DIFFERENT user than the job poster) reviews -> entered_by.
    await decision_service.review_application(
        db_session, principal=org_admin, application_id=app_id, ctx=CTX
    )
    await _set_sla(db_session, app_id, sla_hours=10, entered_hours_ago=9)
    cs, _stage = await _current_row(db_session, app_id)
    assert cs.entered_by == org_admin.user_id

    # The reviewer leaves the org (membership no longer active).
    membership = (
        await db_session.execute(
            select(Membership).where(Membership.user_id == org_admin.user_id)
        )
    ).scalar_one()
    membership.status = "removed"
    await db_session.commit()

    await sla_reminder_service.sweep_sla_reminders(db_session, now=_now())

    rows = (
        await db_session.execute(select(NotificationOutbox).where(
            NotificationOutbox.dedupe_key.like(f"pipeline.sla_reminder:{cs.id}:%")
        ))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].recipient_id == poster_user.id


@pytest.mark.asyncio
async def test_stage_without_sla_hours_never_fires(db_session) -> None:
    _org, _partner, _job, app_id = await _setup_reviewed(db_session)
    cs, stage = await _current_row(db_session, app_id)
    assert stage.sla_hours is None  # V1 default template ships no SLA.

    result = await sla_reminder_service.sweep_sla_reminders(db_session, now=_now())
    assert result["sla_reminders"] == 0
    assert await _sla_outbox_count(db_session, cs.id) == 0


@pytest.mark.asyncio
async def test_wired_through_scheduler_tick(db_session) -> None:
    """Runs via the registered scheduler job name (ADR-0003 wiring), not just the
    bare application-service function."""

    _org, _partner, _job, app_id = await _setup_reviewed(db_session)
    await _set_sla(db_session, app_id, sla_hours=10, entered_hours_ago=9)

    await db_session.rollback()
    results = await runner.tick(
        _now(), session_factory=get_sessionmaker(), only=["pipeline.sla_reminder_sweep"]
    )
    assert results["pipeline.sla_reminder_sweep"]["sla_reminders"] == 1


@pytest.mark.asyncio
async def test_reminder_template_renders_without_error(db_session) -> None:
    """The seeded ``application.stage_sla_reminder`` template renders cleanly when
    the outbox worker drains the row (no leaked provider/template internals)."""

    await ensure_default_templates(db_session)
    _org, _partner, _job, app_id = await _setup_reviewed(db_session)
    await _set_sla(db_session, app_id, sla_hours=10, entered_hours_ago=9)

    await sla_reminder_service.sweep_sla_reminders(db_session, now=_now())
    await db_session.commit()

    result = await process_outbox(db_session, limit=10, now=_now())
    assert result["sent"] >= 1

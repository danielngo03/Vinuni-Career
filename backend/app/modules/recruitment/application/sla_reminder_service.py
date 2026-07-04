"""Pipeline-stage SLA reminder sweep (ADR-0003 scheduler seam).

A ``pipeline_stages.sla_hours`` deadline is tracked per ACTIVE ``candidate_stages``
row from ``entered_at``. This sweep (``pipeline.sla_reminder_sweep``, registered in
``automation.scheduler.jobs``) finds stages approaching (>= 80% of ``sla_hours``
elapsed) or past (>= 100%) their deadline and notifies the ONE person best placed to
act: whoever moved the candidate into the stage (``candidate_stages.entered_by`` —
the closest thing V1 has to an assigned reviewer for that stage instance), falling
back to the job's owner (``jobs.posted_by``) when the reviewer is no longer an
active org member. This is deliberately NOT a broadcast to every org member
(``docs/PARTNER_RBAC_ANALYTICS_SPEC.md``: no feature is hardcoded to "everyone in
the org"; department/ownership scoping applies).

IDEMPOTENT two ways, mirroring ``interview_service.sweep_due_reminders`` /
``offer_service.sweep_offers``:

- ``candidate_stages.sla_reminder_level`` only ever escalates
  (``None -> approaching -> overdue``); a level already notified (or a lower one)
  is never re-sent, so re-ticking a stage that hasn't moved further is a no-op.
- Each notification still carries a per-``(stage, level)`` outbox ``dedupe_key`` as
  defense-in-depth against a crash between "notification enqueued" and "column
  updated" leaving the row re-eligible for one extra tick.

No audit row is written here (consistent with the other reminder/expiry sweeps —
this is a system nudge, not a candidate-state-changing write); the underlying
stage move that IS a write was already audited by ``stage_service``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application import (
    dispatch_service,
    feed_service,
    message_catalog,
)
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.application import job_read_facade
from app.modules.organization.application import org_reporting_facade
from app.modules.recruitment.application import _shared
from app.modules.recruitment.domain import pipeline as pipeline_domain
from app.modules.recruitment.domain.models import Application, CandidateStage, PipelineStage
from app.modules.users.application import user_service

LEVEL_APPROACHING = "approaching"
LEVEL_OVERDUE = "overdue"

# Escalation order; a stage only ever moves forward (never re-sent a same/lower
# level once notified).
_LEVEL_RANK: dict[str | None, int] = {None: 0, LEVEL_APPROACHING: 1, LEVEL_OVERDUE: 2}

_APPROACHING_RATIO = 0.8

_LEVEL_LABEL: dict[str, dict[str, str]] = {
    LEVEL_APPROACHING: {"vi": "sắp đến", "en": "is approaching"},
    LEVEL_OVERDUE: {"vi": "đã quá", "en": "has passed"},
}


def _deadline_label(entered_at: datetime, sla_hours: int) -> str:
    deadline = _shared.as_aware(entered_at) + timedelta(hours=sla_hours)
    return deadline.strftime("%Y-%m-%d %H:%M UTC")


async def _due_rows(
    session: AsyncSession, *, now: datetime
) -> list[tuple[CandidateStage, PipelineStage]]:
    rows = (
        await session.execute(
            select(CandidateStage, PipelineStage)
            .join(PipelineStage, PipelineStage.id == CandidateStage.stage_id)
            .where(
                CandidateStage.status == pipeline_domain.STAGE_ACTIVE,
                PipelineStage.sla_hours.isnot(None),
            )
        )
    ).all()
    due: list[tuple[CandidateStage, PipelineStage]] = []
    for cs, stage in rows:
        if not stage.sla_hours or stage.sla_hours <= 0:
            continue
        elapsed_hours = (now - _shared.as_aware(cs.entered_at)).total_seconds() / 3600
        ratio = elapsed_hours / stage.sla_hours
        if ratio >= 1.0:
            level = LEVEL_OVERDUE
        elif ratio >= _APPROACHING_RATIO:
            level = LEVEL_APPROACHING
        else:
            continue
        if _LEVEL_RANK[cs.sla_reminder_level] >= _LEVEL_RANK[level]:
            continue
        due.append((cs, stage))
    return due


async def _pick_recipient(
    session: AsyncSession, *, app: Application, entered_by
):
    """The pipeline-owner user row to notify, or ``None`` when no active org
    member can be resolved (never a hardcoded org-wide broadcast).

    Preference order: whoever moved the candidate into this stage
    (``candidate_stages.entered_by``), then the job's owner (``jobs.posted_by``).
    Only ACTIVE members of the application's org are eligible recipients.
    """
    org_id = app.org_id
    ordered_candidates = []
    if entered_by is not None:
        ordered_candidates.append(entered_by)
    job_ref = await job_read_facade.get_job_ref(session, app.job_id, include_deleted=True)
    if job_ref is not None and job_ref.posted_by not in ordered_candidates:
        ordered_candidates.append(job_ref.posted_by)
    if not ordered_candidates:
        return None
    active = await org_reporting_facade.active_member_ids(
        session, org_id=org_id, user_ids=ordered_candidates
    )
    for uid in ordered_candidates:
        if uid in active:
            user = await user_service.get_by_id(session, uid)
            if user is not None:
                return user
    return None


async def _notify_one(
    session: AsyncSession,
    *,
    cs: CandidateStage,
    stage: PipelineStage,
    level: str,
    now: datetime,
) -> bool:
    app = (
        await session.execute(
            select(Application).where(
                Application.id == cs.application_id, Application.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if app is None:
        return False

    recipient = await _pick_recipient(session, app=app, entered_by=cs.entered_by)
    if recipient is None:
        return False

    locale = message_catalog.normalize_locale(
        getattr(recipient, "preferred_language", None)
    )
    job_title = await job_read_facade.get_job_title(session, app.job_id) or ""
    level_label = _LEVEL_LABEL[level].get(locale, _LEVEL_LABEL[level]["vi"])
    deadline_label = _deadline_label(cs.entered_at, stage.sla_hours)
    dedupe_key = f"pipeline.sla_reminder:{cs.id}:{level}"

    if await dispatch_service.dedupe_exists(session, dedupe_key=dedupe_key):
        return True

    await enqueue_notification(
        session,
        recipient_id=recipient.id,
        template_key="application.stage_sla_reminder",
        channel="email",
        locale=locale,
        variables={
            "email": recipient.email,
            "name": recipient.full_name or "",
            "job_title": job_title,
            "stage_name": stage.name,
            "level_label": level_label,
            "deadline_label": deadline_label,
        },
        dedupe_key=dedupe_key,
    )
    await feed_service.create_in_app(
        session,
        recipient_id=recipient.id,
        notif_type="recruitment.pipeline_sla_reminder",
        action_url=f"/partner/applications/{app.id}?stage={cs.stage_id}&sla={level}",
        variables={
            "job_title": job_title,
            "stage_name": stage.name,
            "level_label": level_label,
            "deadline_label": deadline_label,
        },
        locale=locale,
    )
    return True


async def sweep_sla_reminders(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Enqueue approaching/overdue SLA reminders for ACTIVE candidate stages.

    Called by the ADR-0003 scheduler (``pipeline.sla_reminder_sweep``). IDEMPOTENT
    (see module docstring). Flush-only — the scheduler owns the commit (mirrors
    ``interview_service.sweep_due_reminders`` / ``offer_service.sweep_offers``).
    """

    now = _shared.as_aware(now) if now is not None else _shared.now()
    due = await _due_rows(session, now=now)

    sent = 0
    for cs, stage in due:
        level = LEVEL_OVERDUE if _stage_ratio(cs, stage, now) >= 1.0 else LEVEL_APPROACHING
        notified = await _notify_one(session, cs=cs, stage=stage, level=level, now=now)
        if notified:
            cs.sla_reminder_level = level
            cs.sla_reminder_sent_at = now
            sent += 1
    await session.flush()
    return {"sla_reminders": sent}


def _stage_ratio(cs: CandidateStage, stage: PipelineStage, now: datetime) -> float:
    elapsed_hours = (now - _shared.as_aware(cs.entered_at)).total_seconds() / 3600
    return elapsed_hours / stage.sla_hours

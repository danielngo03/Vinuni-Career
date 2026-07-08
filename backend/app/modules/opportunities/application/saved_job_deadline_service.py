"""Saved-job application-deadline nudge sweep (student re-engagement).

Notifies a student when a job they SAVED is approaching its application
deadline so they can apply before it closes
(``docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`` §3 — "Job deadline reminders and
saved-job closure"). Two escalating lead-time windows, ``T-48h`` and ``T-24h``.

Product discipline (spec §1 — "career-critical, not marketing spam"):

- Only jobs the student can STILL apply to are nudged: the canonical public
  visibility predicate (``visibility.apply_visible_filter`` at the STUDENT tier —
  published + approved + active + within-deadline + discoverable tier) is applied,
  so a retracted / closed / past-deadline job never nudges.
- A saved job the student has ALREADY applied to is EXCLUDED. The re-engagement
  value only exists for a save the student hasn't acted on yet; nudging someone
  who already applied would be pure spam.
- Only the NARROWEST currently-open window fires per evaluation, so a job saved
  late (deadline already inside T-24h) gets one urgent nudge, not a T-48h and a
  T-24h nudge at once.

IDEMPOTENT (the core acceptance): each nudge carries a per-``(job, user, window)``
outbox ``dedupe_key`` (``saved_job.deadline_nudge:{job}:{user}:{window}``), so a
re-run of the sweep enqueues nothing new — a nudge fires once at its threshold and
never twice. Genuine escalation to a narrower window is a distinct key, so the
T-48h and T-24h nudges each fire once.

Cross-module boundary: ``SavedJob`` + ``Job`` are owned by this module. The
"already applied" check is a READ-ONLY raw ``text()`` query against the
``applications`` table — the same documented cross-module read contract
``competition_service`` uses — so no ``recruitment`` ORM/domain import crosses the
boundary.

No audit row is written here (consistent with every other reminder/expiry sweep —
``interview_service.sweep_due_reminders`` / ``registration_service.sweep_reminders``
/ ``sla_reminder_service``): this is a system nudge, not a state-changing write.
The durable send record is the ``notification_outbox`` row (template key +
recipient + delivery status, spec §4/§7) and the ``notification.sent`` analytics
event emitted when the outbox is drained.

Flush-only — the ADR-0003 scheduler owns the commit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Uuid, bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application import (
    dispatch_service,
    feed_service,
    message_catalog,
)
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.application.visibility import apply_visible_filter
from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job, SavedJob
from app.modules.users.application import user_read_facade, user_service

# Preference category for these nudges (non-mandatory; opt-outable per channel).
_CATEGORY = "job_deadline"
_NOTIF_TYPE = "opportunities.saved_job_deadline"
_TEMPLATE_KEY = "job.saved_deadline"

# Escalating lead-time windows, WIDEST first. Only the narrowest currently-open
# window fires per evaluation (see module docstring).
_WINDOW_48H = "48h"
_WINDOW_24H = "24h"
_DEADLINE_WINDOWS: tuple[tuple[str, timedelta], ...] = (
    (_WINDOW_48H, timedelta(hours=48)),
    (_WINDOW_24H, timedelta(hours=24)),
)
_WIDEST_WINDOW = _DEADLINE_WINDOWS[0][1]

# A saved job is only nudged if it is discoverable/applyable at the student tier.
# This EXCLUDES ``invitation_only`` (and any tier a student may not discover),
# exactly like public discovery + the job-alert dispatch sweep.
_STUDENT_VISIBILITY_LEVELS = lifecycle.visible_levels_for(
    "student", is_authenticated=True
)

_BATCH_ROWS = 500


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _as_aware(dt: datetime) -> datetime:
    """Coerce a possibly-naive timestamp (SQLite reads back naive) to UTC-aware."""

    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _deadline_label(deadline: datetime) -> str:
    return _as_aware(deadline).strftime("%Y-%m-%d %H:%M UTC")


def _open_window(deadline: datetime, now: datetime) -> str | None:
    """The NARROWEST window currently open for ``deadline``, or ``None``.

    A window ``w`` (lead time ``delta``) is open once ``now`` has reached
    ``deadline - delta``. Because ``_DEADLINE_WINDOWS`` is ordered widest-first, the
    last one that satisfies the guard is the narrowest open window — so a job saved
    with < 24h remaining fires only the T-24h nudge, never both at once.
    """

    chosen: str | None = None
    for window, delta in _DEADLINE_WINDOWS:
        if deadline - delta <= now:
            chosen = window
    return chosen


async def _already_applied(
    session: AsyncSession, *, user_id: uuid.UUID, job_id: uuid.UUID
) -> bool:
    """``True`` iff the student has a live (non-withdrawn) application to the job.

    READ-ONLY cross-module query against ``applications`` (mirrors
    ``competition_service._applied_by_student``) — no ``recruitment`` import.
    """

    result = await session.execute(
        text(
            "SELECT 1 FROM applications"
            " WHERE job_id = :job_id AND applicant_id = :user_id"
            " AND status != 'withdrawn' AND deleted_at IS NULL"
            " LIMIT 1"
        ).bindparams(
            bindparam("job_id", type_=Uuid(as_uuid=True)),
            bindparam("user_id", type_=Uuid(as_uuid=True)),
        ),
        {"job_id": job_id, "user_id": user_id},
    )
    return result.first() is not None


async def _enqueue_nudge(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    job: Job,
    window: str,
    deadline: datetime,
) -> int:
    """Enqueue the email (outbox) + in-app feed nudge for one (job, user, window).

    Deduped per ``(job, user, window)`` via the outbox ``dedupe_key`` so a re-run is
    a no-op. Honors the student's ``job_deadline`` preference on BOTH channels:
    ``email='off'`` suppresses only the email; a muted in-app preference is honored
    inside ``feed_service.create_in_app``. Returns ``1`` if anything was enqueued.
    """

    dedupe_key = f"saved_job.deadline_nudge:{job.id}:{user_id}:{window}"
    if await dispatch_service.dedupe_exists(session, dedupe_key=dedupe_key):
        return 0

    student = await user_service.get_by_id(session, user_id)
    locale = message_catalog.normalize_locale(
        getattr(student, "preferred_language", None) if student else None
    )
    deadline_label = _deadline_label(deadline)

    enqueued = False

    # Email channel — only if the student has a real account and hasn't set the
    # category email preference to "off" (PII-safe: only their OWN email/name).
    if student is not None:
        email_setting = await user_read_facade.get_notification_email_setting(
            session, user_id=user_id, category=_CATEGORY
        )
        if email_setting != "off":
            await enqueue_notification(
                session,
                recipient_id=user_id,
                template_key=_TEMPLATE_KEY,
                channel="email",
                locale=locale,
                variables={
                    "email": student.email,
                    "name": student.full_name or "",
                    "job_title": job.title,
                    "deadline_label": deadline_label,
                    "action_url": f"/jobs/{job.id}",
                },
                dedupe_key=dedupe_key,
            )
            enqueued = True

    # In-app feed row (message_catalog copy; no PII in title/body). The category
    # in-app preference is honored inside create_in_app. Window in the action_url
    # keeps the T-48h and T-24h rows distinct (they are separate nudges).
    row = await feed_service.create_in_app(
        session,
        recipient_id=user_id,
        notif_type=_NOTIF_TYPE,
        action_url=f"/jobs/{job.id}?deadline={window}",
        variables={"job_title": job.title, "deadline_label": deadline_label},
        locale=locale,
    )
    if row is not None:
        enqueued = True

    return 1 if enqueued else 0


async def sweep_saved_job_deadlines(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Enqueue deadline nudges for saved, still-applyable, not-yet-applied jobs.

    Called by the ADR-0003 scheduler (``opportunities.saved_job_deadline_sweep``).
    IDEMPOTENT (see module docstring). Flush-only — the scheduler owns the commit.
    """

    now = _as_aware(now) if now is not None else _now()
    horizon = now + _WIDEST_WINDOW

    stmt = (
        apply_visible_filter(
            select(SavedJob.user_id, Job).join(Job, Job.id == SavedJob.job_id),
            levels=_STUDENT_VISIBILITY_LEVELS,
            now=now,
        )
        .where(
            Job.application_deadline.isnot(None),
            Job.application_deadline <= horizon,
        )
        .limit(_BATCH_ROWS)
    )
    rows = (await session.execute(stmt)).all()

    enqueued = 0
    for user_id, job in rows:
        window = _open_window(_as_aware(job.application_deadline), now)
        if window is None:
            continue
        if await _already_applied(session, user_id=user_id, job_id=job.id):
            continue
        enqueued += await _enqueue_nudge(
            session,
            user_id=user_id,
            job=job,
            window=window,
            deadline=_as_aware(job.application_deadline),
        )

    await session.flush()
    return {"deadline_nudges": enqueued}

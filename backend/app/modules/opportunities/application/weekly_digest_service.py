"""Weekly job digest sweeper.

Runs once per week (604 800 s). Queries the top-8 most recently published
active+approved jobs, then enqueues a ``student.weekly_job_digest`` email
for every active student. Idempotent per ISO week: a dedupe_key check
prevents double-sending when the sweep fires more than once in the same week.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application import dispatch_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.domain.models import Job
from app.modules.users.application import user_read_facade

logger = logging.getLogger(__name__)

_TOP_JOBS = 8
_STUDENT_BATCH = 500
_PERSONA = "student"


async def sweep_weekly_digest(session: AsyncSession, *, now: datetime) -> dict[str, int]:
    """Enqueue a weekly job digest for every active student. Idempotent per ISO week."""

    job_rows = (
        await session.execute(
            select(Job.id, Job.title)
            .where(
                Job.status == "active",
                Job.moderation_status == "approved",
                Job.deleted_at.is_(None),
                Job.published_at.isnot(None),
            )
            .order_by(Job.published_at.desc())
            .limit(_TOP_JOBS)
        )
    ).all()

    if not job_rows:
        return {"jobs_found": 0, "digests_enqueued": 0, "digests_skipped": 0}

    iso_year, iso_week, _ = now.date().isocalendar()
    iso_tag = f"{iso_year}-W{iso_week:02d}"
    job_count = len(job_rows)
    job_lines = "\n".join(f"{i + 1}. {row.title}" for i, row in enumerate(job_rows))

    student_rows = await user_read_facade.list_active_persona_contacts(
        session, _PERSONA, limit=_STUDENT_BATCH
    )

    enqueued = skipped = 0
    for row in student_rows:
        dedupe_key = f"student.weekly_digest:{row.id}:{iso_tag}"
        already = await dispatch_service.dedupe_exists(session, dedupe_key=dedupe_key)
        if already:
            skipped += 1
            continue

        await enqueue_notification(
            session,
            recipient_id=row.id,
            template_key="student.weekly_job_digest",
            channel="email",
            locale=row.preferred_language or "vi",
            variables={
                "name": row.full_name or "",
                "email": row.email,
                "job_count": str(job_count),
                "job_lines": job_lines,
                "url": "/student/jobs",
            },
            dedupe_key=dedupe_key,
        )
        enqueued += 1

    await session.commit()
    logger.info(
        "weekly_job_digest.sweep",
        extra={
            "jobs_found": job_count,
            "digests_enqueued": enqueued,
            "digests_skipped": skipped,
        },
    )
    return {"jobs_found": job_count, "digests_enqueued": enqueued, "digests_skipped": skipped}

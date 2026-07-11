"""Saved-jobs (student favourites) service.

Students can save (heart) any publicly-visible job. The save state is
persisted per (user_id, job_id) with idempotent upsert / silent-delete so
the UI can optimistically toggle without worrying about double-saves.

API surface (called from the jobs router):
- ``save_job``   — idempotent save; returns {saved: True}
- ``unsave_job`` — idempotent remove; returns {saved: False}
- ``get_saved_ids`` — set of saved job UUIDs for a user (used to inject
  ``is_saved`` into job list/detail projections)
- ``list_saved_jobs`` — cursor-paginated saved job summaries for the student
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.api import presenters
from app.modules.opportunities.application.visibility import (
    apply_visible_filter,
    guest_levels,
)
from app.modules.opportunities.domain.models import Job, SavedJob
from app.modules.organization.application import org_reporting_facade
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal


def _require_student(principal: Principal) -> None:
    if not principal.is_authenticated or principal.persona != "student":
        raise PermissionDeniedError()


async def save_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
) -> dict:
    """Idempotent save. Returns {saved: True, job_id}."""
    _require_student(principal)

    # Verify the job exists and is publicly visible.
    job = (
        await session.execute(select(Job).where(Job.id == job_id, Job.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if job is None:
        raise ResourceNotFoundError()

    # Upsert-by-conflict: if the row already exists, do nothing.
    try:
        stmt = (
            pg_insert(SavedJob)
            .values(
                id=uuid.uuid4(),
                user_id=principal.user_id,
                job_id=job_id,
                org_id=job.org_id,
            )
            .on_conflict_do_nothing(constraint="uq_saved_jobs_user_job")
        )
        await session.execute(stmt)
        await session.commit()
    except Exception:
        # SQLite (unit tests) fallback: check-then-insert.
        await session.rollback()
        existing = (
            await session.execute(
                select(SavedJob).where(
                    SavedJob.user_id == principal.user_id,
                    SavedJob.job_id == job_id,
                )
            )
        ).scalar_one_or_none()
        if not existing:
            session.add(
                SavedJob(
                    id=uuid.uuid4(),
                    user_id=principal.user_id,
                    job_id=job_id,
                    org_id=job.org_id,
                )
            )
            await session.commit()
    await _record_save_click_metric(session, job=job, principal=principal)
    return {"saved": True, "job_id": str(job_id)}


async def _record_save_click_metric(
    session: AsyncSession, *, job: Job, principal: Principal
) -> None:
    """Best-effort ``save_click`` hook into ``partner_job_metrics_daily``
    (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`). Never blocks the save action."""

    try:
        from app.modules.analytics.application import partner_job_metrics_service as metrics

        source = await metrics.default_source_for_job(session, job_id=job.id)
        student_tier = metrics.student_tier_for_persona(principal.persona)
        major_group, year_group = await metrics.coarse_academic_dims(
            session, user_id=principal.user_id
        )
        await metrics.record_job_metric_event(
            session,
            org_id=job.org_id,
            job_id=job.id,
            event_type="save_click",
            source=source,
            student_tier=student_tier,
            major_group=major_group,
            year_group=year_group,
        )
        await session.commit()
    except Exception:  # noqa: BLE001 — telemetry must never break the save action
        pass


async def unsave_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
) -> dict:
    """Idempotent remove. Returns {saved: False, job_id}."""
    _require_student(principal)
    await session.execute(
        delete(SavedJob).where(
            SavedJob.user_id == principal.user_id,
            SavedJob.job_id == job_id,
        )
    )
    await session.commit()
    return {"saved": False, "job_id": str(job_id)}


async def get_saved_ids(
    session: AsyncSession,
    *,
    principal: Principal,
) -> set[uuid.UUID]:
    """Return the set of job_ids the user has saved (empty for guests)."""
    if not principal.is_authenticated:
        return set()
    rows = (
        (
            await session.execute(
                select(SavedJob.job_id).where(SavedJob.user_id == principal.user_id)
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


async def list_saved_jobs(
    session: AsyncSession,
    *,
    principal: Principal,
    cursor: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int]:
    """Cursor-paginated list of the student's saved jobs (visible only)."""
    _require_student(principal)
    page_limit = clamp_limit(limit)

    # Base: saved rows for this user, joined-filtered to publicly visible jobs.
    from datetime import UTC, datetime

    from sqlalchemy import or_

    now = datetime.now(tz=UTC)

    base = (
        select(SavedJob)
        .join(Job, Job.id == SavedJob.job_id)
        .where(
            SavedJob.user_id == principal.user_id,
            Job.deleted_at.is_(None),
        )
    )
    # Re-use the guest visibility levels so saved jobs that were retracted go away.
    base = apply_visible_filter(base, levels=guest_levels(), now=now)

    decoded = decode_cursor(cursor)
    if decoded is not None:
        anchor_saved = datetime.fromisoformat(decoded["saved_at"])
        anchor_id = uuid.UUID(decoded["id"])
        base = base.where(
            or_(
                SavedJob.saved_at < anchor_saved,
                (SavedJob.saved_at == anchor_saved) & (SavedJob.id < anchor_id),
            )
        )
    base = base.order_by(SavedJob.saved_at.desc(), SavedJob.id.desc()).limit(page_limit + 1)
    saved_rows = list((await session.execute(base)).scalars().all())

    page = build_cursor_page(
        saved_rows,
        limit=page_limit,
        cursor_builder=lambda s: {
            "saved_at": s.saved_at.isoformat(),
            "id": str(s.id),
        },
    )

    # Batch-load jobs + orgs for this page.
    job_ids = [s.job_id for s in page.items]
    if not job_ids:
        return [], page.next_cursor, page.limit

    jobs_map: dict[uuid.UUID, Job] = {}
    if job_ids:
        job_rows = (await session.execute(select(Job).where(Job.id.in_(job_ids)))).scalars().all()
        jobs_map = {j.id: j for j in job_rows}

    org_ids = {j.org_id for j in jobs_map.values()}
    orgs_map = await org_reporting_facade.summaries_for(session, org_ids)

    items = []
    for s in page.items:
        job = jobs_map.get(s.job_id)
        if job is None:
            continue
        summary = presenters.public_job_summary(
            job, company=orgs_map.get(job.org_id), locale=locale, is_saved=True
        )
        items.append(summary)

    return items, page.next_cursor, page.limit


async def get_saved_job_signals(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = 20,
) -> dict:
    """Return lightweight affinity signals from the student's recent saved jobs.

    Used by the recommendation ranker as a saved-affinity personalization signal.
    Returns a privacy-safe dict with:
    - ``employment_types``: unique employment types from saved jobs
    - ``title_tokens``: set of normalized title word tokens
    - ``skills``: union of required + preferred skills from saved jobs
    """

    rows = (
        await session.execute(
            select(Job.employment_type, Job.title, Job.required_skills, Job.preferred_skills)
            .join(SavedJob, SavedJob.job_id == Job.id)
            .where(
                SavedJob.user_id == user_id,
                Job.deleted_at.is_(None),
            )
            .order_by(SavedJob.saved_at.desc())
            .limit(limit)
        )
    ).all()

    employment_types: list[str] = []
    raw_titles: list[str] = []
    skills: list[str] = []
    seen_et: set[str] = set()
    for emp_type, title, req_skills, pref_skills in rows:
        if emp_type and emp_type not in seen_et:
            seen_et.add(emp_type)
            employment_types.append(emp_type)
        if title:
            raw_titles.append(title)
        for sk in req_skills or []:
            if sk not in skills:
                skills.append(str(sk))
        for sk in pref_skills or []:
            if sk not in skills:
                skills.append(str(sk))

    return {
        "employment_types": employment_types,
        "raw_titles": raw_titles,
        "skills": skills[:30],
    }

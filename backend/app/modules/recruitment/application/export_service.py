"""Partner application export — synchronous CSV, < 1 000 rows (B-332).

Exports all applications (including terminal) for one of the caller org's jobs.
Anonymity rules from ``apply_service`` apply: unrevealed anonymous applicants are
shown as their UV handle with no email (never leaked via export).
Stage name is resolved from the ACTIVE ``candidate_stages`` row if present.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.application import job_read_facade
from app.modules.recruitment.domain import lifecycle
from app.modules.recruitment.domain.models import (
    Application,
    CandidateStage,
    PipelineStage,
)
from app.modules.users.application import user_read_facade
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "applications"
_MAX_ROWS = 1000


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def _applicant_label(app: Application, user: user_read_facade.UserContact | None) -> str:
    revealed = app.reveal_approved_at is not None or not app.is_anonymous
    if revealed and user and user.full_name:
        return user.full_name
    handle = (str(app.applicant_id)[:8]).upper()
    return f"UV-{handle}"


def _email(app: Application, user: user_read_facade.UserContact | None) -> str:
    revealed = app.reveal_approved_at is not None or not app.is_anonymous
    if revealed and user:
        return user.email
    return ""


async def export_applications_csv(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    locale: str = "vi",
) -> str:
    """Return a UTF-8 CSV string with all applications for the given job.

    The job must belong to the caller's org; ``applications:read`` is required.
    Capped at _MAX_ROWS to keep the response synchronous and bound.
    """

    job = await job_read_facade.get_job_ref(session, job_id)
    if job is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and (
        principal.org_id is None or principal.org_id != job.org_id
    ):
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "read", resource_org_id=job.org_id
    )

    # All applications (including terminal) ordered newest-first, capped.
    apps = list(
        (
            await session.execute(
                select(Application)
                .where(Application.job_id == job_id, Application.deleted_at.is_(None))
                .order_by(Application.applied_at.desc(), Application.id.desc())
                .limit(_MAX_ROWS)
            )
        )
        .scalars()
        .all()
    )

    if not apps:
        return _empty_csv(locale)

    app_ids = [a.id for a in apps]
    user_ids = list({a.applicant_id for a in apps})

    # Batch-load users (revealed or not — we still load to get the UV handle).
    user_map = await user_read_facade.get_user_contacts(session, user_ids)

    # Batch-load active stage + name in one join.
    stage_rows = (
        await session.execute(
            select(CandidateStage.application_id, PipelineStage.name)
            .join(PipelineStage, PipelineStage.id == CandidateStage.stage_id)
            .where(
                CandidateStage.application_id.in_(app_ids),
                CandidateStage.status == "ACTIVE",
            )
        )
    ).all()
    stage_by_app: dict[uuid.UUID, str] = {r.application_id: r.name for r in stage_rows}

    headers = [
        "application_id",
        "applicant",
        "email",
        "status",
        "stage",
        "applied_at",
        "last_status_at",
        "rejection_reason",
        "is_anonymous",
    ]

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    for app in apps:
        user = user_map.get(app.applicant_id)
        status_display = lifecycle.status_label(app.status, locale=locale)
        writer.writerow(
            [
                str(app.id),
                _applicant_label(app, user),
                _email(app, user),
                status_display,
                stage_by_app.get(app.id, ""),
                _iso(app.applied_at),
                _iso(app.last_status_at),
                app.rejection_reason or "",
                "yes" if app.is_anonymous else "no",
            ]
        )

    return buf.getvalue()


def _empty_csv(locale: str) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        [
            "application_id", "applicant", "email", "status",
            "stage", "applied_at", "last_status_at",
            "rejection_reason", "is_anonymous",
        ]
    )
    return buf.getvalue()

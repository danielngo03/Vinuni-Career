"""Partner application export — synchronous CSV, < 1 000 rows (B-332).

Exports all applications (including terminal) for one of the caller org's jobs.
Each row carries the applicant's real identity (name + email) — an application
always exposes the applicant to a partner who holds ``applications:read``
(owner decision 2026-07-10). Stage name is resolved from the ACTIVE
``candidate_stages`` row if present.
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

# Column catalog for the AI-assistant applicant export (localized headers). The
# assistant lets a recruiter pick which columns to include; unknown/omitted keys
# fall back to _DEFAULT_EXPORT_COLUMNS.
_EXPORT_COLUMN_LABELS: dict[str, dict[str, str]] = {
    "application_id": {"vi": "Mã đơn", "en": "Application ID"},
    "applicant": {"vi": "Ứng viên", "en": "Applicant"},
    "email": {"vi": "Email", "en": "Email"},
    "status": {"vi": "Trạng thái", "en": "Status"},
    "stage": {"vi": "Vòng hiện tại", "en": "Current stage"},
    "applied_at": {"vi": "Ngày ứng tuyển", "en": "Applied at"},
    "last_status_at": {"vi": "Cập nhật gần nhất", "en": "Last update"},
    "rejection_reason": {"vi": "Lý do từ chối", "en": "Rejection reason"},
}
_DEFAULT_EXPORT_COLUMNS = ["applicant", "email", "status", "stage", "applied_at"]


def export_column_keys() -> list[str]:
    """Ordered list of selectable export columns (for the tool schema / UI)."""
    return list(_EXPORT_COLUMN_LABELS)


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def _applicant_label(app: Application, user: user_read_facade.UserContact | None) -> str:
    if user and user.full_name:
        return user.full_name
    return (str(app.applicant_id)[:8]).upper()


def _email(app: Application, user: user_read_facade.UserContact | None) -> str:
    return user.email if user else ""


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
    if not principal.is_superadmin and (principal.org_id is None or principal.org_id != job.org_id):
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=job.org_id)

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
            ]
        )

    return buf.getvalue()


def _empty_csv(locale: str) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        [
            "application_id",
            "applicant",
            "email",
            "status",
            "stage",
            "applied_at",
            "last_status_at",
            "rejection_reason",
        ]
    )
    return buf.getvalue()


def _export_cell(
    col: str,
    app: Application,
    user: user_read_facade.UserContact | None,
    stage_name: str,
    locale: str,
) -> str:
    if col == "application_id":
        return str(app.id)
    if col == "applicant":
        return _applicant_label(app, user)
    if col == "email":
        return _email(app, user)
    if col == "status":
        return lifecycle.status_label(app.status, locale=locale)
    if col == "stage":
        return stage_name
    if col == "applied_at":
        return _iso(app.applied_at)
    if col == "last_status_at":
        return _iso(app.last_status_at)
    if col == "rejection_reason":
        return app.rejection_reason or ""
    return ""


async def export_applications_xlsx(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    stage: str | None = None,
    status: str | None = None,
    columns: list[str] | None = None,
    locale: str = "vi",
) -> tuple[bytes, int, list[str], str]:
    """Build a real .xlsx of a job's applicants for the AI assistant.

    Org-scoped and gated on ``applications:export`` (distinct from ``read`` — the
    partner admin grants export narrowly). Supports an optional ``stage`` name
    filter, ``status`` filter, and a selectable ``columns`` subset. Returns
    ``(xlsx_bytes, row_count, resolved_columns, job_title)``. Each row carries the
    applicant's real identity (name + email).
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    job = await job_read_facade.get_job_ref(session, job_id)
    if job is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and (principal.org_id is None or principal.org_id != job.org_id):
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "export", resource_org_id=job.org_id)

    # Resolve + validate the requested columns (fall back to a sensible default).
    resolved_cols = [c for c in (columns or []) if c in _EXPORT_COLUMN_LABELS]
    if not resolved_cols:
        resolved_cols = list(_DEFAULT_EXPORT_COLUMNS)

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

    app_ids = [a.id for a in apps]
    user_ids = list({a.applicant_id for a in apps})
    user_map = await user_read_facade.get_user_contacts(session, user_ids) if user_ids else {}

    stage_rows = (
        (
            await session.execute(
                select(CandidateStage.application_id, PipelineStage.name)
                .join(PipelineStage, PipelineStage.id == CandidateStage.stage_id)
                .where(
                    CandidateStage.application_id.in_(app_ids),
                    CandidateStage.status == "ACTIVE",
                )
            )
        ).all()
        if app_ids
        else []
    )
    stage_by_app: dict[uuid.UUID, str] = {r.application_id: r.name for r in stage_rows}

    # Apply optional filters (case-insensitive; status matches code or label).
    status_q = (status or "").strip().lower()
    stage_q = (stage or "").strip().lower()

    def _keep(app: Application) -> bool:
        if status_q:
            label = lifecycle.status_label(app.status, locale=locale).lower()
            if status_q not in app.status.lower() and status_q not in label:
                return False
        if stage_q and stage_q not in stage_by_app.get(app.id, "").lower():
            return False
        return True

    rows = [a for a in apps if _keep(a)]

    wb = Workbook()
    ws = wb.active
    ws.title = "Applicants"
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2D5FA6")
    for idx, col in enumerate(resolved_cols, start=1):
        cell = ws.cell(row=1, column=idx, value=_EXPORT_COLUMN_LABELS[col].get(locale, col))
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = 22
    for r_idx, app in enumerate(rows, start=2):
        user = user_map.get(app.applicant_id)
        stage_name = stage_by_app.get(app.id, "")
        for c_idx, col in enumerate(resolved_cols, start=1):
            ws.cell(row=r_idx, column=c_idx, value=_export_cell(col, app, user, stage_name, locale))
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), len(rows), resolved_cols, job.title

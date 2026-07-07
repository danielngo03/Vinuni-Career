"""Job alert CRUD — student-facing subscription management.

Students create named alerts (e.g. "Python internships in Hanoi") that will
trigger in-app + email notifications when matching new jobs are published.
The matching and dispatch runs in a separate Celery periodic task (not this
module). This module handles only create/list/delete/toggle.

Permission: authenticated student (persona == "student") only.
Limit: max ``_MAX_ALERTS_PER_USER`` active alerts per user.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.domain.models import JobAlert
from app.shared.exceptions import (
    ConflictError,
    PermissionDeniedError,
    QuotaExceededError,
    ResourceNotFoundError,
)

_MAX_ALERTS_PER_USER = 10


async def count_alerts_for_user(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Count of active job alerts — for dashboard read models, no auth check."""
    result = await session.execute(
        select(func.count()).where(
            JobAlert.user_id == user_id,
            JobAlert.is_active.is_(True),
        )
    )
    return result.scalar_one()


def _require_student(principal) -> None:
    if principal.persona != "student" and not principal.is_superadmin:
        raise PermissionDeniedError()
    if not principal.user_id:
        raise PermissionDeniedError()


async def list_alerts(
    session: AsyncSession,
    *,
    principal,
) -> list[dict]:
    """Return all job alerts for the authenticated student (newest first)."""
    _require_student(principal)
    rows = (
        await session.execute(
            select(JobAlert)
            .where(
                JobAlert.user_id == principal.user_id,
                JobAlert.is_active.is_(True),
            )
            .order_by(JobAlert.created_at.desc())
        )
    ).scalars().all()
    return [_present(alert) for alert in rows]


async def create_alert(
    session: AsyncSession,
    *,
    principal,
    name: str,
    keywords: str | None = None,
    employment_type: str | None = None,
    location_type: str | None = None,
    province_code: str | None = None,
) -> dict:
    """Create a new job alert for the authenticated student.

    Returns the created alert or raises:
    - ``ForbiddenError`` if the user is not a student.
    - ``LimitExceededError`` if the user already has 10 active alerts.
    - ``ConflictError`` if an alert with the same name already exists.
    """
    _require_student(principal)

    existing_count = (
        await session.execute(
            select(JobAlert)
            .where(
                JobAlert.user_id == principal.user_id,
                JobAlert.is_active.is_(True),
            )
        )
    ).scalars().all()

    if len(existing_count) >= _MAX_ALERTS_PER_USER:
        raise QuotaExceededError(
            details={"limit": _MAX_ALERTS_PER_USER, "current": len(existing_count)}
        )

    name = name.strip()[:120]
    if not name:
        raise ValueError("Alert name is required.")

    alert = JobAlert(
        user_id=principal.user_id,
        name=name,
        keywords=keywords.strip()[:255] if keywords else None,
        employment_type=employment_type or None,
        location_type=location_type or None,
        province_code=province_code or None,
        is_active=True,
    )
    session.add(alert)
    try:
        await session.flush()
    except Exception as exc:
        exc_str = str(exc).lower()
        if (
            "uq_job_alerts_user_name" in exc_str
            or ("job_alerts" in exc_str and "unique" in exc_str)
        ):
            raise ConflictError(
                details={"reason": "alert_name_exists"}
            ) from exc
        raise
    # The request-scoped session (``get_db_session``) does NOT auto-commit on
    # success — every write service in this codebase commits its own
    # transaction (mirrors ``saved_jobs_service``). Without this the flushed row
    # is discarded when the session closes and the alert is silently lost.
    await session.commit()
    await session.refresh(alert)
    return _present(alert)


async def delete_alert(
    session: AsyncSession,
    *,
    principal,
    alert_id: uuid.UUID,
) -> None:
    """Soft-delete (deactivate) a job alert owned by the authenticated student."""
    _require_student(principal)
    result = await session.execute(
        select(JobAlert).where(
            JobAlert.id == alert_id,
            JobAlert.user_id == principal.user_id,
        )
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise ResourceNotFoundError()
    alert.is_active = False
    await session.flush()
    # Persist the soft-delete — the session dependency never commits on success.
    await session.commit()


def _present(alert: JobAlert) -> dict:
    return {
        "id": str(alert.id),
        "name": alert.name,
        "keywords": alert.keywords,
        "employment_type": alert.employment_type,
        "location_type": alert.location_type,
        "province_code": alert.province_code,
        "is_active": alert.is_active,
        "last_sent_at": alert.last_sent_at.isoformat() if alert.last_sent_at else None,
        "created_at": alert.created_at.isoformat(),
    }

"""Partner-to-student job application invitations (partner outreach).

A partner invites a talent-pool student to apply to a specific published job.
Business rules:
- Partner must own the job (same org) and have jobs:write permission.
- At most one ACTIVE (pending, not deleted) invitation per (job, student).
- Invitations expire in 7 days; lazy-expired on read (no background sweep needed
  in V1 — the UI shows the deadline and the service marks status=expired on check).
- When a student "accepts" they are redirected to the formal apply page (CV
  selection is always required — we never auto-apply without a chosen CV).
  The invitation status flips to accepted and the partner receives a notification.
- Declined invitations stay soft-alive so the partner sees the history.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import feed_service as notif_service
from app.modules.opportunities.application import job_read_facade
from app.modules.organization.application import org_reporting_facade
from app.modules.recruitment.domain.models import JobApplicationInvitation
from app.shared.exceptions import (
    AuthRequiredError,
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.pagination import clamp_limit
from app.shared.permissions import Principal, permission_checker

_INVITE_TTL_DAYS = 7
_MAX_MESSAGE_LEN = 500

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(dt: datetime) -> datetime:
    """Coerce a naive datetime (SQLite) to UTC-aware."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def _require_partner(session: AsyncSession, principal: Principal) -> uuid.UUID:
    """Return the partner org_id; raise if caller is not a partner with jobs:write."""
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if not permission_checker.can(principal, "jobs", "write"):
        raise PermissionDeniedError(details={"reason": "partner_only"})
    if principal.org_id is None:
        raise PermissionDeniedError(details={"reason": "no_org"})
    return principal.org_id


async def _get_job(
    session: AsyncSession, job_id: uuid.UUID, org_id: uuid.UUID
) -> job_read_facade.JobRef:
    """Load a published job that belongs to org_id; raise NotFound otherwise."""
    row = await job_read_facade.get_org_scoped_job_ref(
        session, job_id=job_id, org_id=org_id, active_only=True
    )
    if row is None:
        raise ResourceNotFoundError()
    return row


async def _get_org_name(session: AsyncSession, org_id: uuid.UUID) -> str:
    name = await org_reporting_facade.display_name_for(session, org_id)
    return name or ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def send_invite(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    student_id: uuid.UUID,
    message: str | None = None,
    locale: str = "vi",
) -> dict:
    """Partner sends a job invitation to a student.

    Returns the invitation dict. Raises ConflictError if an active invitation
    already exists for this (job, student) pair.
    """
    org_id = await _require_partner(session, principal)

    # Validate message length.
    if message and len(message.strip()) > _MAX_MESSAGE_LEN:
        raise ValidationFailedError(details={"message": f"max {_MAX_MESSAGE_LEN} chars"})

    # Confirm the job is published + owned by this partner.
    job = await _get_job(session, job_id, org_id)

    # No duplicate active invitation.
    existing = (
        await session.execute(
            select(JobApplicationInvitation).where(
                and_(
                    JobApplicationInvitation.job_id == job_id,
                    JobApplicationInvitation.student_id == student_id,
                    JobApplicationInvitation.status == "pending",
                    JobApplicationInvitation.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(details={"reason": "duplicate_active_invitation"})

    now = _now()
    expires_at = now + timedelta(days=_INVITE_TTL_DAYS)
    invite = JobApplicationInvitation(
        job_id=job_id,
        student_id=student_id,
        inviting_org_id=org_id,
        inviting_user_id=principal.user_id,
        message=message.strip() if message else None,
        status="pending",
        expires_at=expires_at,
    )
    session.add(invite)
    await session.flush()

    company_name = await _get_org_name(session, org_id)
    await notif_service.create_in_app(
        session,
        recipient_id=student_id,
        notif_type="recruitment.job_invitation_received",
        action_url=f"/student/invitations/{str(invite.id)}",
        sender_id=principal.user_id,
        variables={"company_name": company_name, "job_title": job.title},
        locale=locale,
    )

    return _present(invite, job_title=job.title, company_name=company_name)


async def list_student_invitations(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> list[dict]:
    """Student lists their job invitations.

    Lazily marks expired invitations before returning. Default: pending only.
    """
    if not principal.is_authenticated:
        raise AuthRequiredError()

    page_limit = clamp_limit(limit)
    filter_status = status or "pending"

    stmt = (
        select(JobApplicationInvitation)
        .where(
            JobApplicationInvitation.student_id == principal.user_id,
            JobApplicationInvitation.deleted_at.is_(None),
        )
        .order_by(JobApplicationInvitation.created_at.desc())
        .limit(page_limit)
    )

    if filter_status != "all":
        stmt = stmt.where(JobApplicationInvitation.status == filter_status)

    invitations = list((await session.execute(stmt)).scalars().all())
    titles = await job_read_facade.get_job_titles(session, (inv.job_id for inv in invitations))
    names = await org_reporting_facade.display_names_for(
        session, (inv.inviting_org_id for inv in invitations)
    )

    now = _now()
    out = []
    for inv in invitations:
        # Lazy expiry: flip pending→expired if TTL passed.
        if inv.status == "pending" and _as_aware(inv.expires_at) < now:
            inv.status = "expired"
            await session.flush()
        out.append(
            _present(
                inv,
                job_title=titles.get(inv.job_id) or "",
                company_name=names.get(inv.inviting_org_id) or "",
            )
        )
    return out


async def respond_invitation(
    session: AsyncSession,
    *,
    principal: Principal,
    invitation_id: uuid.UUID,
    response: str,
    locale: str = "vi",
    ctx: RequestContext | None = None,
) -> dict:
    """Student accepts or declines a pending invitation.

    ``response`` must be "accepted" or "declined". On accept, an Application
    is created via apply_service (non-anonymous).
    """
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if response not in ("accepted", "declined"):
        raise ValidationFailedError(details={"response": "accepted or declined"})
    if isinstance(invitation_id, str):
        invitation_id = uuid.UUID(invitation_id)

    inv = (
        await session.execute(
            select(JobApplicationInvitation).where(
                JobApplicationInvitation.id == invitation_id,
                JobApplicationInvitation.student_id == principal.user_id,
                JobApplicationInvitation.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if inv is None:
        raise ResourceNotFoundError()

    # Lazy expiry check.
    now = _now()
    if inv.status == "pending" and _as_aware(inv.expires_at) < now:
        inv.status = "expired"
        await session.flush()

    if inv.status != "pending":
        raise ConflictError(details={"reason": inv.status})

    inv.status = response
    inv.responded_at = now
    await session.flush()

    job = await job_read_facade.get_job_ref(session, inv.job_id, include_deleted=True)
    job_title = job.title if job is not None else ""
    company_name = await _get_org_name(session, inv.inviting_org_id)

    if response == "accepted":
        # Accepted means the student intends to apply. They will be directed to
        # the formal apply page (CV selection is always required). We only notify
        # the partner that the student showed interest; the actual Application row
        # is created by the student on the apply page.
        await notif_service.create_in_app(
            session,
            recipient_id=inv.inviting_user_id,
            notif_type="recruitment.job_invitation_accepted",
            action_url=f"/partner/jobs/{str(inv.job_id)}/candidates",
            variables={"job_title": job_title},
            locale=locale,
        )

    result = _present(inv, job_title=job_title, company_name=company_name)
    if response == "accepted":
        result["apply_url"] = f"/jobs/{str(inv.job_id)}"
    return result


async def get_invitation(
    session: AsyncSession,
    *,
    principal: Principal,
    invitation_id: uuid.UUID,
) -> dict:
    """Student fetches a single invitation detail."""
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if isinstance(invitation_id, str):
        invitation_id = uuid.UUID(invitation_id)

    inv = (
        await session.execute(
            select(JobApplicationInvitation).where(
                JobApplicationInvitation.id == invitation_id,
                JobApplicationInvitation.student_id == principal.user_id,
                JobApplicationInvitation.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if inv is None:
        raise ResourceNotFoundError()

    now = _now()
    if inv.status == "pending" and _as_aware(inv.expires_at) < now:
        inv.status = "expired"
        await session.flush()

    job_title = await job_read_facade.get_job_title(session, inv.job_id) or ""
    company_name = await _get_org_name(session, inv.inviting_org_id)
    return _present(inv, job_title=job_title, company_name=company_name)


def _present(
    inv: JobApplicationInvitation,
    *,
    job_title: str,
    company_name: str,
) -> dict:
    return {
        "id": str(inv.id),
        "job_id": str(inv.job_id),
        "job_title": job_title,
        "company_name": company_name,
        "message": inv.message,
        "status": inv.status,
        "expires_at": inv.expires_at.isoformat(),
        "responded_at": inv.responded_at.isoformat() if inv.responded_at else None,
        "created_at": inv.created_at.isoformat(),
    }

"""Employer CRM surface (B-553): profile quality, seats, campus ownership,
event/campaign + hiring-outcome rollups, risk/trust flags, and university-only
notes.

Two viewer shapes are supported by every read here:

- **Self view**: the partner org looking at its own record
  (``organizations:read`` on its own ``org_id``).
- **University oversight view**: a university-staff actor looking at any
  partner org (``partners:read``/``partners:manage`` on their own university
  org — the same "acting org must be university" gate ``partner_registration_
  service`` already uses; the *target* org id is a query argument, not the
  tenant-isolation scope).

Risk flags and university notes are university-only in both directions: a
partner org can never read or write them, regardless of its own grants.

Note on module boundaries: the event/campaign/hiring rollups below read
``opportunities``/``advertising``/``recruitment`` ORM rows directly (read-only,
single grouped aggregates, no writes). This mirrors the "read model, not a
heavy live join" rule but does create an organization -> {opportunities,
advertising, recruitment} import that does not yet have a dedicated read-facade
on the producing side (unlike ``org_reporting_facade`` for the reverse
direction). Flagged in the handoff for ``system-architect`` to decide whether
those modules should expose narrow facades instead.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.organization.application.errors import NotUniversityActorError
from app.modules.organization.domain import catalog
from app.modules.organization.domain.models import (
    Membership,
    Organization,
    OrganizationNote,
    OrganizationRiskFlag,
)
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RECENT_ACTIVITY_WINDOW_DAYS = 90


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id, actor_org_id=principal.org_id,
        ip=ctx.ip, user_agent=ctx.user_agent,
    )


async def _get_org(session: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = (
        await session.execute(
            select(Organization).where(
                Organization.id == org_id, Organization.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if org is None:
        raise ResourceNotFoundError()
    return org


async def _is_university_actor(session: AsyncSession, principal: Principal) -> bool:
    if principal.org_id is None:
        return False
    from app.modules.organization.application import org_reporting_facade

    return await org_reporting_facade.is_university_org(session, principal.org_id)


async def _authorize_view(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID
) -> None:
    """Self-view (own org, ``organizations:read``) OR university oversight view."""

    if principal.org_id == org_id:
        permission_checker.require(principal, "organizations", "read", resource_org_id=org_id)
        return
    permission_checker.require(principal, "partners", "read")
    if not principal.is_superadmin and not await _is_university_actor(session, principal):
        raise NotUniversityActorError()


async def _require_university_manage(
    session: AsyncSession, *, principal: Principal
) -> None:
    permission_checker.require(principal, "partners", "manage")
    if not principal.is_superadmin and not await _is_university_actor(session, principal):
        raise NotUniversityActorError()


# --------------------------------------------------------------------------- #
# Profile quality score (deterministic rubric, never a fabricated AI score)   #
# --------------------------------------------------------------------------- #


async def _active_recruiter_count(session: AsyncSession, *, org_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(Membership)
            .where(Membership.org_id == org_id, Membership.status == "active")
        )
    ).scalar_one()


async def _has_recent_activity(session: AsyncSession, *, org_id: uuid.UUID) -> bool:
    """Proxy signal: any job in an active/pending-review/draft state.

    A simplification documented for the architecture follow-up: a full "recent
    activity" signal would also weigh event/application/campaign recency.
    """

    from app.modules.opportunities.application import dashboard_read as jobs_read

    counts = await jobs_read.count_org_jobs_by_status(session, org_id=org_id)
    return sum(counts.values()) > 0


def compute_profile_quality(
    org: Organization,
    *,
    active_recruiter_count: int,
    has_recent_activity: bool,
) -> dict:
    """Deterministic 0-100 completeness rubric. Never an AI/model score."""

    checks: list[tuple[str, bool, int]] = [
        ("logo", bool(org.logo_path), 15),
        ("description", bool(org.description and len(org.description.strip()) >= 50), 15),
        ("verified", bool(org.is_verified), 20),
        ("industry", bool(org.industry or org.industry_id), 10),
        ("company_size", bool(org.company_size), 10),
        ("website", bool(org.website_url), 10),
        ("has_active_recruiter", active_recruiter_count > 0, 10),
        ("recent_activity", has_recent_activity, 10),
    ]
    score = sum(points for _, met, points in checks if met)
    breakdown = [
        {"check": name, "met": met, "points": points} for name, met, points in checks
    ]
    missing = [name for name, met, _ in checks if not met]
    return {"score": score, "breakdown": breakdown, "missing": missing}


async def get_profile_quality(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID
) -> dict:
    await _authorize_view(session, principal=principal, org_id=org_id)
    org = await _get_org(session, org_id)
    active_recruiters = await _active_recruiter_count(session, org_id=org_id)
    recent = await _has_recent_activity(session, org_id=org_id)
    return compute_profile_quality(
        org, active_recruiter_count=active_recruiters, has_recent_activity=recent
    )


# --------------------------------------------------------------------------- #
# Recruiter seats                                                             #
# --------------------------------------------------------------------------- #


async def recruiter_seats_summary(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID
) -> dict:
    """Active member count vs the org's seat cap (``-1`` = unlimited)."""

    await _authorize_view(session, principal=principal, org_id=org_id)
    org = await _get_org(session, org_id)
    used = await _active_recruiter_count(session, org_id=org_id)
    limit = org.max_team_members
    return {
        "used": used,
        "limit": limit if limit != -1 else None,
        "unlimited": limit == -1,
        "at_capacity": limit != -1 and used >= limit,
    }


# --------------------------------------------------------------------------- #
# Campus relationship owner                                                   #
# --------------------------------------------------------------------------- #


async def get_campus_owner(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID
) -> dict:
    await _require_university_manage(session, principal=principal)
    org = await _get_org(session, org_id)
    return {"campus_relationship_owner_id": (
        str(org.campus_relationship_owner_id)
        if org.campus_relationship_owner_id else None
    )}


async def set_campus_owner(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID,
    owner_user_id: uuid.UUID | None,
    ctx: RequestContext,
) -> dict:
    await _require_university_manage(session, principal=principal)
    org = await _get_org(session, org_id)

    if owner_user_id is not None:
        from app.modules.users.application import user_read_facade

        contact = await user_read_facade.get_user_contact(session, owner_user_id)
        if contact is None:
            raise ValidationFailedError(
                "Không tìm thấy người phụ trách được chọn.",
                details={"reason": "owner_user_not_found"},
            )

    before = org.campus_relationship_owner_id
    org.campus_relationship_owner_id = owner_user_id
    org.version += 1
    await session.flush()
    await write_audit(
        session, action="organization.campus_owner_set",
        resource_type="organization", resource_id=org.id,
        context=_audit_ctx(principal, ctx),
        before={"campus_relationship_owner_id": str(before) if before else None},
        after={
            "campus_relationship_owner_id": (
                str(owner_user_id) if owner_user_id else None
            )
        },
    )
    await session.commit()
    return {
        "campus_relationship_owner_id": (
            str(owner_user_id) if owner_user_id else None
        )
    }


# --------------------------------------------------------------------------- #
# Risk / trust flags (university/superadmin only, replaces bare trust_level)  #
# --------------------------------------------------------------------------- #


def _risk_flag_view(flag: OrganizationRiskFlag) -> dict:
    return {
        "id": str(flag.id),
        "flag_type": flag.flag_type,
        "severity": flag.severity,
        "note": flag.note,
        "raised_by": str(flag.raised_by),
        "raised_at": flag.raised_at.isoformat() if flag.raised_at else None,
        "resolved_by": str(flag.resolved_by) if flag.resolved_by else None,
        "resolved_at": flag.resolved_at.isoformat() if flag.resolved_at else None,
        "resolution_note": flag.resolution_note,
        "is_resolved": flag.resolved_at is not None,
    }


async def list_risk_flags(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID
) -> list[dict]:
    await _require_university_manage(session, principal=principal)
    await _get_org(session, org_id)
    rows = (
        await session.execute(
            select(OrganizationRiskFlag)
            .where(OrganizationRiskFlag.org_id == org_id)
            .order_by(OrganizationRiskFlag.raised_at.desc())
        )
    ).scalars().all()
    return [_risk_flag_view(r) for r in rows]


async def raise_risk_flag(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID,
    flag_type: str,
    severity: str,
    note: str | None,
    ctx: RequestContext,
) -> dict:
    await _require_university_manage(session, principal=principal)
    await _get_org(session, org_id)
    if severity not in catalog.RISK_FLAG_SEVERITIES:
        raise ValidationFailedError(
            "Mức độ nghiêm trọng không hợp lệ.", details={"reason": "invalid_severity"}
        )
    if principal.user_id is None:
        raise ResourceNotFoundError()

    flag = OrganizationRiskFlag(
        org_id=org_id, flag_type=flag_type, severity=severity, note=note,
        raised_by=principal.user_id,
    )
    session.add(flag)
    await session.flush()
    await write_audit(
        session, action="organization.risk_flag_raised", resource_type="organization",
        resource_id=org_id, context=_audit_ctx(principal, ctx),
        after={"flag_id": str(flag.id), "flag_type": flag_type, "severity": severity},
    )
    await session.commit()
    return _risk_flag_view(flag)


async def resolve_risk_flag(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID,
    flag_id: uuid.UUID,
    resolution_note: str | None,
    ctx: RequestContext,
) -> dict:
    await _require_university_manage(session, principal=principal)
    await _get_org(session, org_id)
    flag = (
        await session.execute(
            select(OrganizationRiskFlag).where(
                OrganizationRiskFlag.id == flag_id, OrganizationRiskFlag.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if flag is None:
        raise ResourceNotFoundError()
    if flag.resolved_at is not None:
        return _risk_flag_view(flag)

    flag.resolved_by = principal.user_id
    flag.resolved_at = datetime.now(tz=UTC)
    flag.resolution_note = resolution_note
    await session.flush()
    await write_audit(
        session, action="organization.risk_flag_resolved", resource_type="organization",
        resource_id=org_id, context=_audit_ctx(principal, ctx),
        after={"flag_id": str(flag.id)},
    )
    await session.commit()
    return _risk_flag_view(flag)


# --------------------------------------------------------------------------- #
# University-only CRM notes                                                   #
# --------------------------------------------------------------------------- #


def _note_view(note: OrganizationNote) -> dict:
    return {
        "id": str(note.id),
        "body": note.body,
        "created_by": str(note.created_by),
        "created_at": note.created_at.isoformat() if note.created_at else None,
    }


async def list_notes(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID
) -> list[dict]:
    await _require_university_manage(session, principal=principal)
    await _get_org(session, org_id)
    rows = (
        await session.execute(
            select(OrganizationNote)
            .where(OrganizationNote.org_id == org_id)
            .order_by(OrganizationNote.created_at.desc())
        )
    ).scalars().all()
    return [_note_view(n) for n in rows]


async def create_note(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID,
    body: str,
    ctx: RequestContext,
) -> dict:
    await _require_university_manage(session, principal=principal)
    await _get_org(session, org_id)
    if not body.strip():
        raise ValidationFailedError(
            "Ghi chú không được để trống.", details={"reason": "empty_note"}
        )
    if principal.user_id is None:
        raise ResourceNotFoundError()

    note = OrganizationNote(org_id=org_id, body=body.strip(), created_by=principal.user_id)
    session.add(note)
    await session.flush()
    await write_audit(
        session, action="organization.note_created", resource_type="organization",
        resource_id=org_id, context=_audit_ctx(principal, ctx),
        after={"note_id": str(note.id)},
    )
    await session.commit()
    return _note_view(note)


# --------------------------------------------------------------------------- #
# Event / campaign history rollup                                             #
# --------------------------------------------------------------------------- #


async def event_campaign_rollup(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID
) -> dict:
    await _authorize_view(session, principal=principal, org_id=org_id)
    await _get_org(session, org_id)

    from app.modules.advertising.application import inventory_facade
    from app.modules.opportunities.application import dashboard_read as jobs_read

    events_by_status = await jobs_read.count_events_by_status_for_org(
        session, org_id=org_id
    )
    campaigns_by_status = await inventory_facade.count_campaigns_by_status_for_org(
        session, org_id=org_id
    )

    return {
        "events": {
            "total": sum(events_by_status.values()),
            "by_status": events_by_status,
        },
        "campaigns": {
            "total": sum(campaigns_by_status.values()),
            "by_status": campaigns_by_status,
        },
    }


# --------------------------------------------------------------------------- #
# Hiring outcomes aggregate                                                   #
# --------------------------------------------------------------------------- #


async def hiring_outcomes(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID, months: int = 12
) -> dict:
    await _authorize_view(session, principal=principal, org_id=org_id)
    await _get_org(session, org_id)

    from app.modules.recruitment.application import dashboard_read as recruitment_read

    return await recruitment_read.hiring_outcomes_for_org(
        session, org_id=org_id, months=months
    )

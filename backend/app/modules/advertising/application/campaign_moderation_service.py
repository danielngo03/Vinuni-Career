"""University / admin oversight of the campaign allocation engine (spec §7.0).

Approval = oversight of DISCLOSURE + TARGETING + SPEND; a campaign serves only
after the university approves it (and its go-live window opens). The university may
also record manual/bank-transfer payment, pause or disable any campaign
immediately, relabel a NON-paid campaign's public inventory class (never mislabel
paid inventory as editorial), and inspect the live allocation plan.

The university-only gate mirrors the placement moderator gate (superadmin OR a
member of a ``university`` org holding ``advertising:moderate``) so a partner
Admin's ``*:*`` can never self-approve. RBAC + audit + tenant rules live here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.advertising.api import campaign_presenters
from app.modules.advertising.application import campaign_reporting
from app.modules.advertising.application.campaign_errors import (
    CampaignVersionConflictError,
    IllegalCampaignTransitionError,
    InvalidCampaignFieldError,
    PaidDisclosureImmutableError,
)
from app.modules.advertising.domain import campaign as lifecycle
from app.modules.advertising.domain import disclosure as disclosure_vocab
from app.modules.advertising.domain.models import AdAllocation, AdCampaign
from app.modules.auth.application.context import RequestContext
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.moderation import (
    REASON_OTHER,
    REASON_REQUIRES_NOTE,
    is_valid_reason_code,
)
from app.shared.pagination import clamp_limit
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "advertising"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _use_lock() -> bool:
    return get_settings().database_url.startswith("postgresql")


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def _require_advertising_moderator(session: AsyncSession, principal: Principal) -> None:
    if principal.is_superadmin:
        return
    permission_checker.require(principal, _RESOURCE, "moderate")
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "university_only"})


async def _load(session: AsyncSession, campaign_id: uuid.UUID, *, lock: bool = False) -> AdCampaign:
    stmt = select(AdCampaign).where(
        AdCampaign.id == campaign_id, AdCampaign.deleted_at.is_(None)
    )
    if lock and _use_lock():
        stmt = stmt.with_for_update()
    campaign = (await session.execute(stmt)).scalar_one_or_none()
    if campaign is None:
        raise ResourceNotFoundError()
    return campaign


async def _present(session: AsyncSession, c: AdCampaign, *, locale: str) -> dict:
    impressions = await campaign_reporting.impressions_today_for(
        session, campaign_id=c.id, now=_now()
    )
    return campaign_presenters.campaign(
        c, locale=locale, admin=True, impressions_today=impressions
    )


def _validate_reason_code(reason_code: str | None, *, reason: str | None) -> str:
    code = reason_code or REASON_OTHER
    if not is_valid_reason_code(code):
        raise InvalidCampaignFieldError(field="reason_code")
    if code in REASON_REQUIRES_NOTE and not (reason and reason.strip()):
        raise InvalidCampaignFieldError(field="reason_code")
    return code


# --------------------------------------------------------------------------- #
# Queue / spend oversight                                                    #
# --------------------------------------------------------------------------- #


async def list_review_queue(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    org_id: uuid.UUID | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], int, dict]:
    """All campaigns (filterable) + a spend/health roll-up (admin only)."""

    await _require_advertising_moderator(session, principal)
    page_limit = clamp_limit(limit)
    filters: list = [AdCampaign.deleted_at.is_(None)]
    if status is not None:
        filters.append(AdCampaign.status == status)
    if org_id is not None:
        filters.append(AdCampaign.org_id == org_id)

    stmt = (
        select(AdCampaign)
        .where(*filters)
        .order_by(AdCampaign.submitted_at.desc().nulls_last(), AdCampaign.created_at.desc())
        .limit(page_limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(select(func.count()).select_from(AdCampaign).where(*filters))
    ).scalar_one()

    active_spend = (
        await session.execute(
            select(func.coalesce(func.sum(AdCampaign.spent_amount), 0)).where(
                AdCampaign.deleted_at.is_(None),
                AdCampaign.status.in_([lifecycle.ACTIVE, lifecycle.PAUSED, lifecycle.ENDED]),
            )
        )
    ).scalar_one()
    pending = (
        await session.execute(
            select(func.count())
            .select_from(AdCampaign)
            .where(
                AdCampaign.deleted_at.is_(None),
                AdCampaign.status == lifecycle.PENDING_REVIEW,
            )
        )
    ).scalar_one()
    items = [await _present(session, r, locale=locale) for r in rows]
    spend = {
        "active_count": sum(1 for r in rows if r.status == lifecycle.ACTIVE),
        "pending_review_count": int(pending),
        "total_spend_amount": f"{active_spend:.2f}",
        "currency": "VND",
    }
    return items, int(total), spend


# --------------------------------------------------------------------------- #
# Approve / reject                                                            #
# --------------------------------------------------------------------------- #


def _try_activate_inline(campaign: AdCampaign, *, now: datetime) -> None:
    """Serve immediately if the go-live window is already open (approved → active).

    V1 serving gate = ``approved`` + window-open. Manual payment is recorded for
    spend oversight (``mark_paid``) but is not a hard serving gate, so a
    university-approved campaign can go live for demo/testing without a blocking
    payment step. Budget still caps total spend via the delivery accounting.
    """

    if campaign.status != lifecycle.APPROVED:
        return
    if _aware(campaign.start_at) <= now < _aware(campaign.end_at):
        campaign.status = lifecycle.ACTIVE
        campaign.activated_at = campaign.activated_at or now


async def approve_campaign(
    session: AsyncSession,
    *,
    principal: Principal,
    campaign_id: uuid.UUID,
    note: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_advertising_moderator(session, principal)
    campaign = await _load(session, campaign_id, lock=True)
    if version is not None and version != campaign.version:
        raise CampaignVersionConflictError()
    if campaign.status in (lifecycle.APPROVED, lifecycle.ACTIVE):
        return await _present(session, campaign, locale=locale)  # idempotent
    if not lifecycle.can_transition("approve", campaign.status):
        raise IllegalCampaignTransitionError(event="approve")

    now = _now()
    campaign.status = lifecycle.APPROVED
    campaign.moderation_note = note
    campaign.approved_by = principal.user_id
    campaign.approved_at = now
    campaign.version += 1
    _try_activate_inline(campaign, now=now)
    await session.flush()
    await write_audit(
        session,
        action="advertising.campaign_approved",
        resource_type="ad_campaign",
        resource_id=campaign.id,
        context=_audit_ctx(principal, ctx),
        after={"status": campaign.status, "org_id": str(campaign.org_id)},
    )
    await session.commit()
    await session.refresh(campaign)
    return await _present(session, campaign, locale=locale)


async def reject_campaign(
    session: AsyncSession,
    *,
    principal: Principal,
    campaign_id: uuid.UUID,
    reason: str,
    reason_code: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_advertising_moderator(session, principal)
    if not reason or not reason.strip():
        raise ValidationFailedError(details={"reason": "reason_required"})
    code = _validate_reason_code(reason_code, reason=reason)
    campaign = await _load(session, campaign_id, lock=True)
    if version is not None and version != campaign.version:
        raise CampaignVersionConflictError()
    if campaign.status == lifecycle.REJECTED:
        return await _present(session, campaign, locale=locale)  # idempotent
    if not lifecycle.can_transition("reject", campaign.status):
        raise IllegalCampaignTransitionError(event="reject")

    campaign.status = lifecycle.REJECTED
    campaign.moderation_note = reason.strip()
    campaign.moderation_reason_code = code
    campaign.rejected_at = _now()
    campaign.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.campaign_rejected",
        resource_type="ad_campaign",
        resource_id=campaign.id,
        context=_audit_ctx(principal, ctx),
        after={"status": campaign.status, "reason_code": code, "org_id": str(campaign.org_id)},
    )
    await session.commit()
    await session.refresh(campaign)
    return await _present(session, campaign, locale=locale)


# --------------------------------------------------------------------------- #
# Manual payment (bank-transfer spend oversight)                              #
# --------------------------------------------------------------------------- #


async def mark_paid(
    session: AsyncSession,
    *,
    principal: Principal,
    campaign_id: uuid.UUID,
    payment_reference: str,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_advertising_moderator(session, principal)
    if not payment_reference or not payment_reference.strip():
        raise ValidationFailedError(details={"reason": "payment_reference_required"})
    campaign = await _load(session, campaign_id, lock=True)
    if version is not None and version != campaign.version:
        raise CampaignVersionConflictError()

    now = _now()
    campaign.paid_at = campaign.paid_at or now
    campaign.payment_reference = payment_reference.strip()
    campaign.paid_by = principal.user_id
    campaign.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.campaign_paid",
        resource_type="ad_campaign",
        resource_id=campaign.id,
        context=_audit_ctx(principal, ctx),
        after={
            "paid": True,
            "payment_reference": campaign.payment_reference,
            "org_id": str(campaign.org_id),
        },
    )
    await session.commit()
    await session.refresh(campaign)
    return await _present(session, campaign, locale=locale)


# --------------------------------------------------------------------------- #
# Pause / disable any campaign immediately (university oversight)              #
# --------------------------------------------------------------------------- #


async def admin_pause(
    session: AsyncSession,
    *,
    principal: Principal,
    campaign_id: uuid.UUID,
    reason: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_advertising_moderator(session, principal)
    campaign = await _load(session, campaign_id, lock=True)
    if version is not None and version != campaign.version:
        raise CampaignVersionConflictError()
    if campaign.status == lifecycle.PAUSED:
        return await _present(session, campaign, locale=locale)  # idempotent
    if not lifecycle.can_transition("pause", campaign.status):
        raise IllegalCampaignTransitionError(event="pause")
    campaign.status = lifecycle.PAUSED
    campaign.paused_at = _now()
    if reason and reason.strip():
        campaign.moderation_note = reason.strip()
    campaign.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.campaign_paused",
        resource_type="ad_campaign",
        resource_id=campaign.id,
        context=_audit_ctx(principal, ctx),
        after={"status": campaign.status, "by": "university", "org_id": str(campaign.org_id)},
    )
    await session.commit()
    await session.refresh(campaign)
    return await _present(session, campaign, locale=locale)


async def admin_disable(
    session: AsyncSession,
    *,
    principal: Principal,
    campaign_id: uuid.UUID,
    reason: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Force a campaign to ``ended`` immediately (disable-any oversight)."""

    await _require_advertising_moderator(session, principal)
    campaign = await _load(session, campaign_id, lock=True)
    if version is not None and version != campaign.version:
        raise CampaignVersionConflictError()
    if campaign.status in lifecycle.TERMINAL_STATES:
        return await _present(session, campaign, locale=locale)  # idempotent
    if not lifecycle.can_transition("end", campaign.status):
        raise IllegalCampaignTransitionError(event="end")
    campaign.status = lifecycle.ENDED
    campaign.ended_at = _now()
    if reason and reason.strip():
        campaign.moderation_note = reason.strip()
    campaign.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.campaign_disabled",
        resource_type="ad_campaign",
        resource_id=campaign.id,
        context=_audit_ctx(principal, ctx),
        after={"status": campaign.status, "by": "university", "org_id": str(campaign.org_id)},
    )
    await session.commit()
    await session.refresh(campaign)
    return await _present(session, campaign, locale=locale)


# --------------------------------------------------------------------------- #
# Disclosure-class relabel (compliance-guarded editorial control)             #
# --------------------------------------------------------------------------- #


async def set_disclosure_class(
    session: AsyncSession,
    *,
    principal: Principal,
    campaign_id: uuid.UUID,
    disclosure_class: str,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_advertising_moderator(session, principal)
    if not disclosure_vocab.is_valid_disclosure_class(disclosure_class):
        raise InvalidCampaignFieldError(field="disclosure_class")
    campaign = await _load(session, campaign_id, lock=True)
    if version is not None and version != campaign.version:
        raise CampaignVersionConflictError()
    # Never mislabel PAID inventory as curated/strategic/featured.
    if campaign.paid_at is not None and not disclosure_vocab.is_paid(disclosure_class):
        raise PaidDisclosureImmutableError()
    if campaign.disclosure_class == disclosure_class:
        return await _present(session, campaign, locale=locale)  # idempotent

    before = campaign.disclosure_class
    campaign.disclosure_class = disclosure_class
    campaign.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.campaign_disclosure_class_set",
        resource_type="ad_campaign",
        resource_id=campaign.id,
        context=_audit_ctx(principal, ctx),
        before={"disclosure_class": before},
        after={"disclosure_class": disclosure_class, "org_id": str(campaign.org_id)},
    )
    await session.commit()
    await session.refresh(campaign)
    return await _present(session, campaign, locale=locale)


# --------------------------------------------------------------------------- #
# Allocation-plan oversight                                                   #
# --------------------------------------------------------------------------- #


async def list_allocations(
    session: AsyncSession,
    *,
    principal: Principal,
    surface: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Recent allocation-decision records for university oversight (coarse only)."""

    await _require_advertising_moderator(session, principal)
    page_limit = clamp_limit(limit)
    stmt = select(AdAllocation)
    if surface is not None:
        stmt = stmt.where(AdAllocation.surface == surface)
    stmt = stmt.order_by(AdAllocation.allocated_at.desc()).limit(page_limit)
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        {
            "id": str(r.id),
            "campaign_id": str(r.campaign_id),
            "slot_code": r.slot_code,
            "surface": r.surface,
            "segment_key": r.segment_key,
            "position": r.position,
            "match_reason": r.match_reason,
            "pacing_state": r.pacing_state,
            "allocated_at": r.allocated_at.isoformat() if r.allocated_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        }
        for r in rows
    ]

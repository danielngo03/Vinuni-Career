"""University / admin advertising oversight: queue, approve, reject, mark-paid,
and disable-any (ADR-0009 §3/§7/§8/§9.4).

Approval = oversight of **disclosure + spend** (university); payment = **money
received** (admin manual/bank-transfer ``mark_paid``). Both are preconditions to
``active``: activation is gated on ``status=approved AND paid_at IS NOT NULL AND
window-open`` and fires **inline** from ``approve``/``mark_paid`` when the window is
already open (else the scheduler activation sweep picks it up). The
university-only gate mirrors ``opportunities.moderation_service._require_university_
moderator`` (superadmin OR member of a ``university`` org holding
``advertising:moderate``) so a partner Admin's ``*:*`` cannot self-approve.

RBAC + audit + tenant rules live here, not in routers. University can **disable any
placement immediately** (``admin_cancel``) → flags recompute OFF (PRD §13.6).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.advertising.api import presenters
from app.modules.advertising.application import (
    activation_service,
    creative_service,
    notify,
)
from app.modules.advertising.application.errors import (
    IllegalPlacementTransitionError,
    InvalidCreativeFieldError,
    InvalidModerationReasonError,
    PaidDisclosureImmutableError,
    PlacementAlreadyClaimedError,
    PlacementVersionConflictError,
)
from app.modules.advertising.domain import creatives as creative_vocab
from app.modules.advertising.domain import disclosure as disclosure_vocab
from app.modules.advertising.domain import lifecycle
from app.modules.advertising.domain.models import (
    AdPackage,
    CampaignCreative,
    SponsoredPlacement,
)
from app.modules.auth.application.context import RequestContext
from app.modules.opportunities.application import sponsorship_facade
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AppError,
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


def _use_for_update() -> bool:
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


async def _load(
    session: AsyncSession, placement_id: uuid.UUID, *, lock: bool = False
) -> SponsoredPlacement | None:
    stmt = select(SponsoredPlacement).where(
        SponsoredPlacement.id == placement_id,
        SponsoredPlacement.deleted_at.is_(None),
    )
    if lock and _use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def _present(session: AsyncSession, placement: SponsoredPlacement, *, locale: str) -> dict:
    pkg = (
        await session.execute(select(AdPackage).where(AdPackage.id == placement.package_id))
    ).scalar_one_or_none()
    ref = await sponsorship_facade.load_target(
        session, target_type=placement.target_type, target_id=placement.target_id
    )
    creatives = await creative_service.load_for_placement(session, placement.id)
    return presenters.placement(
        placement,
        locale=locale,
        pkg=pkg,
        target_title=ref.title if ref else None,
        admin=True,
        creatives=creatives,
    )


# --------------------------------------------------------------------------- #
# Queue / spend oversight                                                    #
# --------------------------------------------------------------------------- #


async def list_all(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    org_id: uuid.UUID | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], int, dict]:
    """All placements (filterable by status/org) + a spend roll-up (admin only)."""

    await _require_advertising_moderator(session, principal)
    page_limit = clamp_limit(limit)
    base_filters: list = [SponsoredPlacement.deleted_at.is_(None)]
    if status is not None:
        base_filters.append(SponsoredPlacement.status == status)
    if org_id is not None:
        base_filters.append(SponsoredPlacement.org_id == org_id)

    stmt = (
        select(SponsoredPlacement)
        .where(*base_filters)
        .order_by(
            SponsoredPlacement.submitted_at.desc().nulls_last(),
            SponsoredPlacement.created_at.desc(),
        )
        .limit(page_limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(
            select(func.count()).select_from(SponsoredPlacement).where(*base_filters)
        )
    ).scalar_one()

    # Spend oversight roll-up: total frozen price of active placements.
    active_spend = (
        await session.execute(
            select(func.coalesce(func.sum(SponsoredPlacement.price_amount), 0)).where(
                SponsoredPlacement.deleted_at.is_(None),
                SponsoredPlacement.status == lifecycle.ACTIVE,
            )
        )
    ).scalar_one()
    pending = (
        await session.execute(
            select(func.count())
            .select_from(SponsoredPlacement)
            .where(
                SponsoredPlacement.deleted_at.is_(None),
                SponsoredPlacement.status == lifecycle.PENDING_APPROVAL,
            )
        )
    ).scalar_one()
    items = [await _present(session, r, locale=locale) for r in rows]
    spend = {
        "active_count": sum(1 for r in rows if r.status == lifecycle.ACTIVE),
        "pending_approval_count": int(pending),
        "active_spend_amount": f"{active_spend:.2f}",
        "currency": "VND",
    }
    return items, int(total), spend


# --------------------------------------------------------------------------- #
# Approve / reject                                                            #
# --------------------------------------------------------------------------- #


async def approve_placement(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    note: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_advertising_moderator(session, principal)
    placement = await _load(session, placement_id, lock=True)
    if placement is None:
        raise ResourceNotFoundError()
    if version is not None and version != placement.version:
        raise PlacementVersionConflictError()
    if placement.status == lifecycle.APPROVED:
        return await _present(session, placement, locale=locale)  # idempotent
    if not lifecycle.can_transition("approve", placement.status):
        raise IllegalPlacementTransitionError(event="approve")

    now = _now()
    placement.status = lifecycle.APPROVED
    placement.moderation_note = note
    placement.approved_by = principal.user_id
    placement.approved_at = now
    placement.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.placement_approved",
        resource_type="advertising_placement",
        resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        after={"status": placement.status, "org_id": str(placement.org_id)},
    )
    await notify.notify_partner(
        session,
        placement=placement,
        template_key="advertising.approved",
    )
    # Inline activation if already paid + window open (instant go-live).
    await activation_service.try_activate_inline(
        session, placement=placement, now=now, actor=principal
    )
    await session.commit()
    await session.refresh(placement)
    return await _present(session, placement, locale=locale)


def _validate_reason_code(reason_code: str | None, *, reason: str | None) -> str:
    code = reason_code or REASON_OTHER
    if not is_valid_reason_code(code):
        raise InvalidModerationReasonError()
    if code in REASON_REQUIRES_NOTE and not (reason and reason.strip()):
        raise InvalidModerationReasonError()
    return code


async def reject_placement(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
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
    placement = await _load(session, placement_id, lock=True)
    if placement is None:
        raise ResourceNotFoundError()
    if version is not None and version != placement.version:
        raise PlacementVersionConflictError()
    if placement.status == lifecycle.REJECTED:
        return await _present(session, placement, locale=locale)  # idempotent
    if not lifecycle.can_transition("reject", placement.status):
        raise IllegalPlacementTransitionError(event="reject")

    placement.status = lifecycle.REJECTED
    placement.moderation_note = reason.strip()
    placement.moderation_reason_code = code
    placement.claimed_by = None
    placement.claimed_at = None
    placement.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.placement_rejected",
        resource_type="advertising_placement",
        resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        after={"status": placement.status, "reason_code": code, "org_id": str(placement.org_id)},
    )
    await notify.notify_partner(
        session,
        placement=placement,
        template_key="advertising.rejected",
        extra={"reason": reason.strip()},
    )
    await session.commit()
    await session.refresh(placement)
    return await _present(session, placement, locale=locale)


# --------------------------------------------------------------------------- #
# Claim / assign                                                              #
# --------------------------------------------------------------------------- #


async def claim_placement(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Claim a pending-approval placement for review (concurrency-safe)."""

    await _require_advertising_moderator(session, principal)
    placement = await _load(session, placement_id, lock=True)
    if placement is None:
        raise ResourceNotFoundError()
    if placement.status != lifecycle.PENDING_APPROVAL:
        raise IllegalPlacementTransitionError(event="claim")
    if placement.claimed_by == principal.user_id:
        return await _present(session, placement, locale=locale)  # idempotent
    if placement.claimed_by is not None:
        raise PlacementAlreadyClaimedError()

    now = _now()
    result = await session.execute(
        update(SponsoredPlacement)
        .where(
            SponsoredPlacement.id == placement_id,
            SponsoredPlacement.claimed_by.is_(None),
            SponsoredPlacement.version == placement.version,
        )
        .values(
            claimed_by=principal.user_id,
            claimed_at=now,
            version=SponsoredPlacement.version + 1,
        )
    )
    if getattr(result, "rowcount", 0) == 0:
        raise PlacementAlreadyClaimedError()
    await session.flush()
    await write_audit(
        session,
        action="advertising.placement_claimed",
        resource_type="advertising_placement",
        resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        after={"claimed_by": str(principal.user_id), "org_id": str(placement.org_id)},
    )
    await session.commit()
    await session.refresh(placement)
    return await _present(session, placement, locale=locale)


# --------------------------------------------------------------------------- #
# Bulk approve / reject                                                       #
# --------------------------------------------------------------------------- #


async def bulk_approve_placements(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_ids: list[uuid.UUID],
    ctx: RequestContext,
    locale: str = "vi",
) -> list[dict]:
    results: list[dict] = []
    for placement_id in placement_ids:
        try:
            data = await approve_placement(
                session,
                principal=principal,
                placement_id=placement_id,
                ctx=ctx,
                locale=locale,
            )
            results.append({"id": str(placement_id), "success": True, "placement": data})
        except AppError as exc:
            await session.rollback()
            results.append(
                {
                    "id": str(placement_id),
                    "success": False,
                    "error_code": exc.code,
                    "message": exc.message,
                }
            )
    return results


async def bulk_reject_placements(
    session: AsyncSession,
    *,
    principal: Principal,
    items: list[dict],
    ctx: RequestContext,
    locale: str = "vi",
) -> list[dict]:
    results: list[dict] = []
    for item in items:
        placement_id = item["id"]
        try:
            data = await reject_placement(
                session,
                principal=principal,
                placement_id=placement_id,
                reason=item.get("reason", ""),
                reason_code=item.get("reason_code"),
                ctx=ctx,
                locale=locale,
            )
            results.append({"id": str(placement_id), "success": True, "placement": data})
        except AppError as exc:
            await session.rollback()
            results.append(
                {
                    "id": str(placement_id),
                    "success": False,
                    "error_code": exc.code,
                    "message": exc.message,
                }
            )
    return results


# --------------------------------------------------------------------------- #
# Escalation -> human review queue                                            #
# --------------------------------------------------------------------------- #


async def escalate_placement(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    reason_code: str | None = None,
    note: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_advertising_moderator(session, principal)
    code = _validate_reason_code(reason_code, reason=note)
    placement = await _load(session, placement_id, lock=True)
    if placement is None:
        raise ResourceNotFoundError()

    if note and note.strip():
        placement.moderation_note = note.strip()
    placement.moderation_reason_code = code
    placement.version += 1
    await session.flush()

    await write_audit(
        session,
        action="advertising.placement_escalated",
        resource_type="advertising_placement",
        resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        after={"reason_code": code, "org_id": str(placement.org_id)},
    )

    from app.modules.moderation.application import review_queue_service

    await review_queue_service.enqueue(
        session,
        source=review_queue_service.SOURCE_MODERATOR_ESCALATION,
        resource_type="advertising_placement",
        resource_id=placement.id,
        org_id=placement.org_id,
        severity="high",
        findings={
            "reason_code": code,
            "note": (note or "").strip(),
            "escalated_by": str(principal.user_id),
        },
    )
    await session.commit()
    await session.refresh(placement)
    return await _present(session, placement, locale=locale)


# --------------------------------------------------------------------------- #
# Manual payment (bank-transfer)                                              #
# --------------------------------------------------------------------------- #


async def mark_paid(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    payment_reference: str,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_advertising_moderator(session, principal)
    if not payment_reference or not payment_reference.strip():
        raise ValidationFailedError(details={"reason": "payment_reference_required"})
    placement = await _load(session, placement_id, lock=True)
    if placement is None:
        raise ResourceNotFoundError()
    if version is not None and version != placement.version:
        raise PlacementVersionConflictError()
    if placement.status not in (lifecycle.PENDING_APPROVAL, lifecycle.APPROVED):
        raise IllegalPlacementTransitionError(event="mark_paid")

    now = _now()
    placement.paid_at = placement.paid_at or now
    placement.payment_reference = payment_reference.strip()
    placement.paid_by = principal.user_id
    placement.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.placement_paid",
        resource_type="advertising_placement",
        resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        # Spend metadata only (no PII); the reference is intentionally recorded.
        after={
            "paid": True,
            "payment_reference": placement.payment_reference,
            "org_id": str(placement.org_id),
        },
    )
    await notify.notify_partner(
        session,
        placement=placement,
        template_key="advertising.payment_recorded",
    )
    # Inline activation if already approved + window open.
    await activation_service.try_activate_inline(
        session, placement=placement, now=now, actor=principal
    )
    await session.commit()
    await session.refresh(placement)
    return await _present(session, placement, locale=locale)


# --------------------------------------------------------------------------- #
# Disable any placement immediately (university oversight)                    #
# --------------------------------------------------------------------------- #


async def admin_cancel(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    reason: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_advertising_moderator(session, principal)
    placement = await _load(session, placement_id, lock=True)
    if placement is None:
        raise ResourceNotFoundError()
    if version is not None and version != placement.version:
        raise PlacementVersionConflictError()
    if placement.status in lifecycle.TERMINAL_STATES:
        return await _present(session, placement, locale=locale)  # idempotent
    if not lifecycle.can_transition("cancel", placement.status):
        raise IllegalPlacementTransitionError(event="cancel")

    was_active = placement.status == lifecycle.ACTIVE
    placement.status = lifecycle.CANCELLED
    placement.cancelled_at = _now()
    if reason and reason.strip():
        placement.moderation_note = reason.strip()
    placement.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.placement_cancelled",
        resource_type="advertising_placement",
        resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        after={"status": placement.status, "by": "university", "org_id": str(placement.org_id)},
    )
    if was_active:
        await activation_service.recompute_target_flags(
            session,
            target_type=placement.target_type,
            target_id=placement.target_id,
            actor=principal,
            reason="placement_disabled",
        )
    await session.commit()
    await session.refresh(placement)
    return await _present(session, placement, locale=locale)


# --------------------------------------------------------------------------- #
# Disclosure-class relabel (university editorial control)                      #
# --------------------------------------------------------------------------- #


async def set_disclosure_class(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    disclosure_class: str,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """University relabels a placement's public inventory class (spec §4/§6).

    Compliance guard: PAID inventory (a placement that has been paid) can never be
    relabelled to a non-paid editorial/partnership class — the non-removable paid
    disclosure must keep showing. Marking a placement ``paid_sponsored`` is always
    allowed (it only ever strengthens disclosure).
    """

    await _require_advertising_moderator(session, principal)
    if not disclosure_vocab.is_valid_disclosure_class(disclosure_class):
        raise InvalidCreativeFieldError(field="disclosure_class")
    placement = await _load(session, placement_id, lock=True)
    if placement is None:
        raise ResourceNotFoundError()
    if version is not None and version != placement.version:
        raise PlacementVersionConflictError()

    # Never mislabel paid inventory as curated/strategic/featured.
    if placement.paid_at is not None and not disclosure_vocab.is_paid(disclosure_class):
        raise PaidDisclosureImmutableError()

    if placement.disclosure_class == disclosure_class:
        return await _present(session, placement, locale=locale)  # idempotent

    before = placement.disclosure_class
    placement.disclosure_class = disclosure_class
    placement.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.placement_disclosure_class_set",
        resource_type="advertising_placement",
        resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        before={"disclosure_class": before},
        after={"disclosure_class": disclosure_class, "org_id": str(placement.org_id)},
    )
    await session.commit()
    await session.refresh(placement)
    return await _present(session, placement, locale=locale)


# --------------------------------------------------------------------------- #
# Creative review (university approve/reject of the uploaded banner)           #
# --------------------------------------------------------------------------- #


async def _load_creative(
    session: AsyncSession, creative_id: uuid.UUID, *, lock: bool = False
) -> CampaignCreative | None:
    stmt = select(CampaignCreative).where(
        CampaignCreative.id == creative_id,
        CampaignCreative.deleted_at.is_(None),
    )
    if lock and _use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def review_creative(
    session: AsyncSession,
    *,
    principal: Principal,
    creative_id: uuid.UUID,
    decision: str,
    note: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """University approves/rejects an uploaded creative (spec §6 university flow).

    Only an ``approved`` creative on an active placement is ever served publicly,
    so this is the gate that lets a banner go live. ``decision`` is ``approve`` or
    ``reject``; a rejection requires a note.
    """

    await _require_advertising_moderator(session, principal)
    if decision == "approve":
        new_status = creative_vocab.CREATIVE_APPROVED
    elif decision == "reject":
        new_status = creative_vocab.CREATIVE_REJECTED
        if not note or not note.strip():
            raise ValidationFailedError(details={"reason": "reason_required"})
    else:
        raise InvalidCreativeFieldError(field="decision")

    creative = await _load_creative(session, creative_id, lock=True)
    if creative is None:
        raise ResourceNotFoundError()
    if version is not None and version != creative.version:
        raise PlacementVersionConflictError()
    if creative.moderation_status == new_status:
        return presenters.creative(creative, locale=locale)  # idempotent

    creative.moderation_status = new_status
    creative.moderation_note = note.strip() if note else None
    creative.reviewed_by = principal.user_id
    creative.version += 1
    await session.flush()
    await write_audit(
        session,
        action=f"advertising.creative_{new_status}",
        resource_type="advertising_creative",
        resource_id=creative.id,
        context=_audit_ctx(principal, ctx),
        after={"moderation_status": new_status, "placement_id": str(creative.placement_id)},
    )
    await session.commit()
    await session.refresh(creative)
    return presenters.creative(creative, locale=locale)

"""Partner advertiser surface for the campaign-grade allocation engine (spec §7.0).

Create / edit / submit-for-review / pause / resume / end / delete / get / list-mine
for budgeted, coarse-targeted ad campaigns. RBAC is enforced HERE (not routers) via
``permission_checker`` (``advertising`` capability) plus org-scoped tenant
isolation: a partner only ever sees / mutates its own org's campaigns, and a
cross-org (or unknown) access returns ``404`` — never ``403`` — so resources are
not enumerable. Every write records an audit row in the caller's transaction.

Gates:
- targeting is validated STRICTLY (``domain.targeting.validate_campaign_targeting``)
  → a GPS / sensitive dimension is rejected ``422``; only coarse dimensions persist.
- ``submit`` requires ``disclosure_confirmed=true`` → else ``422``; it is rejected
  ``409 active_campaign_limit`` if it would exceed the per-org concurrency cap.
- The CPM (internal spend/pacing rate) is frozen at create from config; it is never
  a partner-facing "bid".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.advertising.api import campaign_presenters
from app.modules.advertising.application.campaign_errors import (
    ActiveCampaignLimitError,
    CampaignDisclosureRequiredError,
    CampaignNotEditableError,
    CampaignVersionConflictError,
    ForbiddenTargetingError,
    IllegalCampaignTransitionError,
    InvalidCampaignFieldError,
    UnknownTargetingError,
)
from app.modules.advertising.application.campaign_reporting import impressions_today_for
from app.modules.advertising.domain import ad_slots
from app.modules.advertising.domain import campaign as lifecycle
from app.modules.advertising.domain import targeting as targeting_vocab
from app.modules.advertising.domain.models import AdCampaign
from app.modules.auth.application.context import RequestContext
from app.modules.opportunities.application import sponsorship_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.moderation import compute_due_by
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "advertising"
_TARGET_TYPES = frozenset({"job", "event"})


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _validated_targeting(raw: dict | None) -> dict:
    try:
        return targeting_vocab.validate_campaign_targeting(raw)
    except targeting_vocab.ForbiddenTargetingDimension as exc:
        raise ForbiddenTargetingError(dimension=exc.dimension) from exc
    except targeting_vocab.UnknownTargetingDimension as exc:
        raise UnknownTargetingError(dimension=exc.dimension) from exc


def _clean_creative(raw: dict | None) -> dict:
    """Keep only the public banner descriptor fields; drop anything else."""

    c = raw or {}
    out: dict[str, object] = {}
    for key in ("headline", "body", "image_ref", "click_target", "alt_vi", "alt_en"):
        value = c.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()[:600]
    return out


def _parse_budget(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidCampaignFieldError(field="budget_amount") from exc
    if amount <= 0:
        raise InvalidCampaignFieldError(field="budget_amount")
    return amount.quantize(Decimal("0.01"))


async def _validate_target(
    session: AsyncSession, *, principal: Principal, target_type: str | None, target_id
) -> tuple[str | None, uuid.UUID | None]:
    """Validate an OPTIONAL promoted job/event target the campaign owns (or 404)."""

    if target_type is None and target_id is None:
        return None, None
    if target_type not in _TARGET_TYPES or target_id is None:
        raise InvalidCampaignFieldError(field="target_type")
    ref = await sponsorship_facade.load_target(
        session, target_type=target_type, target_id=target_id
    )
    if ref is None or (not principal.is_superadmin and ref.org_id != principal.org_id):
        raise ResourceNotFoundError()
    return target_type, target_id


async def _load_owned(
    session: AsyncSession, *, principal: Principal, campaign_id: uuid.UUID, lock: bool = False
) -> AdCampaign:
    stmt = select(AdCampaign).where(
        AdCampaign.id == campaign_id, AdCampaign.deleted_at.is_(None)
    )
    if lock and get_settings().database_url.startswith("postgresql"):
        stmt = stmt.with_for_update()
    campaign = (await session.execute(stmt)).scalar_one_or_none()
    if campaign is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and campaign.org_id != principal.org_id:
        raise ResourceNotFoundError()
    return campaign


async def _present(session: AsyncSession, c: AdCampaign, *, locale: str) -> dict:
    impressions = await impressions_today_for(session, campaign_id=c.id, now=_now())
    return campaign_presenters.campaign(c, locale=locale, impressions_today=impressions)


# --------------------------------------------------------------------------- #
# Create / update                                                             #
# --------------------------------------------------------------------------- #


async def create_campaign(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "create", resource_org_id=principal.org_id)
    assert principal.user_id is not None

    objective = payload["objective"]
    surface = payload["surface"]
    pacing = payload.get("pacing", lifecycle.PACING_EVEN)
    if not lifecycle.is_valid_objective(objective):
        raise InvalidCampaignFieldError(field="objective")
    if not ad_slots.is_valid_surface(surface):
        raise InvalidCampaignFieldError(field="surface")
    if not lifecycle.is_valid_pacing(pacing):
        raise InvalidCampaignFieldError(field="pacing")

    start_at = _aware(payload["start_at"])
    end_at = _aware(payload["end_at"])
    if end_at <= start_at:
        raise InvalidCampaignFieldError(field="end_at")

    budget = _parse_budget(payload["budget_amount"])
    targeting = _validated_targeting(payload.get("targeting"))
    creative = _clean_creative(payload.get("creative"))
    target_type, target_id = await _validate_target(
        session,
        principal=principal,
        target_type=payload.get("target_type"),
        target_id=payload.get("target_id"),
    )

    settings = get_settings()
    campaign = AdCampaign(
        org_id=principal.org_id,
        created_by=principal.user_id,
        name=str(payload["name"]).strip()[:160],
        objective=objective,
        surface=surface,
        budget_amount=budget,
        spent_amount=Decimal("0"),
        cpm_amount=Decimal(settings.advertising_default_cpm_vnd),
        currency="VND",
        pacing=pacing,
        start_at=start_at,
        end_at=end_at,
        status=lifecycle.DRAFT,
        targeting=targeting,
        creative=creative,
        target_type=target_type,
        target_id=target_id,
        disclosure_confirmed=bool(payload.get("disclosure_confirmed", False)),
    )
    session.add(campaign)
    await session.flush()
    await write_audit(
        session,
        action="advertising.campaign_created",
        resource_type="ad_campaign",
        resource_id=campaign.id,
        context=_audit_ctx(principal, ctx),
        after={
            "status": campaign.status,
            "surface": surface,
            "objective": objective,
            "budget_amount": f"{budget:.2f}",
            "targeting_dimensions": sorted(targeting.keys()),
        },
    )
    await session.commit()
    await session.refresh(campaign)
    return await _present(session, campaign, locale=locale)


_UPDATABLE = {
    "name",
    "objective",
    "surface",
    "pacing",
    "budget_amount",
    "start_at",
    "end_at",
    "targeting",
    "creative",
    "target_type",
    "target_id",
    "disclosure_confirmed",
}


async def update_campaign(
    session: AsyncSession,
    *,
    principal: Principal,
    campaign_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    campaign = await _load_owned(session, principal=principal, campaign_id=campaign_id, lock=True)
    permission_checker.require(principal, _RESOURCE, "edit", resource_org_id=campaign.org_id)
    if campaign.status not in lifecycle.EDITABLE_STATES:
        raise CampaignNotEditableError()

    expected_version = payload.pop("version", None)
    if expected_version is not None and expected_version != campaign.version:
        raise CampaignVersionConflictError()

    changed: list[str] = []
    if "name" in payload:
        campaign.name = str(payload["name"]).strip()[:160]
        changed.append("name")
    if "objective" in payload:
        if not lifecycle.is_valid_objective(payload["objective"]):
            raise InvalidCampaignFieldError(field="objective")
        campaign.objective = payload["objective"]
        changed.append("objective")
    if "surface" in payload:
        if not ad_slots.is_valid_surface(payload["surface"]):
            raise InvalidCampaignFieldError(field="surface")
        campaign.surface = payload["surface"]
        changed.append("surface")
    if "pacing" in payload:
        if not lifecycle.is_valid_pacing(payload["pacing"]):
            raise InvalidCampaignFieldError(field="pacing")
        campaign.pacing = payload["pacing"]
        changed.append("pacing")
    if "budget_amount" in payload:
        campaign.budget_amount = _parse_budget(payload["budget_amount"])
        changed.append("budget_amount")
    if "start_at" in payload and payload["start_at"] is not None:
        campaign.start_at = _aware(payload["start_at"])
        changed.append("start_at")
    if "end_at" in payload and payload["end_at"] is not None:
        campaign.end_at = _aware(payload["end_at"])
        changed.append("end_at")
    if _aware(campaign.end_at) <= _aware(campaign.start_at):
        raise InvalidCampaignFieldError(field="end_at")
    if "targeting" in payload:
        campaign.targeting = _validated_targeting(payload["targeting"])
        changed.append("targeting")
    if "creative" in payload:
        campaign.creative = _clean_creative(payload["creative"])
        changed.append("creative")
    if "target_type" in payload or "target_id" in payload:
        target_type, target_id = await _validate_target(
            session,
            principal=principal,
            target_type=payload.get("target_type"),
            target_id=payload.get("target_id"),
        )
        campaign.target_type = target_type
        campaign.target_id = target_id
        changed.append("target")
    if "disclosure_confirmed" in payload:
        campaign.disclosure_confirmed = bool(payload["disclosure_confirmed"])
        changed.append("disclosure_confirmed")

    if changed:
        campaign.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.campaign_updated",
        resource_type="ad_campaign",
        resource_id=campaign.id,
        context=_audit_ctx(principal, ctx),
        after={"fields": sorted(changed)},
    )
    await session.commit()
    await session.refresh(campaign)
    return await _present(session, campaign, locale=locale)


# --------------------------------------------------------------------------- #
# Submit (disclosure + concurrency cap)                                       #
# --------------------------------------------------------------------------- #


async def _count_in_flight(
    session: AsyncSession, *, org_id: uuid.UUID, exclude_id: uuid.UUID
) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(AdCampaign)
            .where(
                AdCampaign.org_id == org_id,
                AdCampaign.deleted_at.is_(None),
                AdCampaign.id != exclude_id,
                AdCampaign.status.in_(list(lifecycle.IN_FLIGHT_STATES)),
            )
        )
    ).scalar_one()


async def submit_campaign(
    session: AsyncSession,
    *,
    principal: Principal,
    campaign_id: uuid.UUID,
    ctx: RequestContext,
    version: int | None = None,
    disclosure_confirmed: bool | None = None,
    locale: str = "vi",
) -> dict:
    campaign = await _load_owned(session, principal=principal, campaign_id=campaign_id, lock=True)
    permission_checker.require(principal, _RESOURCE, "submit", resource_org_id=campaign.org_id)
    if version is not None and version != campaign.version:
        raise CampaignVersionConflictError()
    if not lifecycle.can_transition("submit", campaign.status):
        raise IllegalCampaignTransitionError(event="submit")

    if disclosure_confirmed is not None:
        campaign.disclosure_confirmed = bool(disclosure_confirmed)
    if not campaign.disclosure_confirmed:
        raise CampaignDisclosureRequiredError()

    limit = get_settings().advertising_max_active_campaigns_per_org
    in_flight = await _count_in_flight(session, org_id=campaign.org_id, exclude_id=campaign.id)
    if in_flight >= limit:
        raise ActiveCampaignLimitError(limit=limit)

    now = _now()
    campaign.status = lifecycle.PENDING_REVIEW
    campaign.submitted_at = now
    campaign.due_by = compute_due_by(
        now, sla_hours=get_settings().advertising_moderation_sla_hours
    )
    campaign.moderation_note = None
    campaign.moderation_reason_code = None
    campaign.rejected_at = None
    campaign.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.campaign_submitted",
        resource_type="ad_campaign",
        resource_id=campaign.id,
        context=_audit_ctx(principal, ctx),
        after={"status": campaign.status},
    )
    await session.commit()
    await session.refresh(campaign)
    return await _present(session, campaign, locale=locale)


# --------------------------------------------------------------------------- #
# Pause / resume / end (partner)                                              #
# --------------------------------------------------------------------------- #


async def _transition(
    session: AsyncSession,
    *,
    principal: Principal,
    campaign_id: uuid.UUID,
    event: str,
    action: str,
    ctx: RequestContext,
    version: int | None,
    locale: str,
) -> dict:
    campaign = await _load_owned(session, principal=principal, campaign_id=campaign_id, lock=True)
    permission_checker.require(principal, _RESOURCE, "edit", resource_org_id=campaign.org_id)
    if version is not None and version != campaign.version:
        raise CampaignVersionConflictError()
    if not lifecycle.can_transition(event, campaign.status):
        raise IllegalCampaignTransitionError(event=event)

    now = _now()
    campaign.status = lifecycle.target_state(event)
    if event == "pause":
        campaign.paused_at = now
    elif event == "resume":
        campaign.activated_at = campaign.activated_at or now
    elif event == "end":
        campaign.ended_at = now
    campaign.version += 1
    await session.flush()
    await write_audit(
        session,
        action=action,
        resource_type="ad_campaign",
        resource_id=campaign.id,
        context=_audit_ctx(principal, ctx),
        after={"status": campaign.status, "by": "partner"},
    )
    await session.commit()
    await session.refresh(campaign)
    return await _present(session, campaign, locale=locale)


async def pause_campaign(session, *, principal, campaign_id, ctx, version=None, locale="vi"):
    return await _transition(
        session,
        principal=principal,
        campaign_id=campaign_id,
        event="pause",
        action="advertising.campaign_paused",
        ctx=ctx,
        version=version,
        locale=locale,
    )


async def resume_campaign(session, *, principal, campaign_id, ctx, version=None, locale="vi"):
    return await _transition(
        session,
        principal=principal,
        campaign_id=campaign_id,
        event="resume",
        action="advertising.campaign_resumed",
        ctx=ctx,
        version=version,
        locale=locale,
    )


async def end_campaign(session, *, principal, campaign_id, ctx, version=None, locale="vi"):
    return await _transition(
        session,
        principal=principal,
        campaign_id=campaign_id,
        event="end",
        action="advertising.campaign_ended",
        ctx=ctx,
        version=version,
        locale=locale,
    )


async def delete_campaign(
    session: AsyncSession,
    *,
    principal: Principal,
    campaign_id: uuid.UUID,
    ctx: RequestContext,
) -> None:
    campaign = await _load_owned(session, principal=principal, campaign_id=campaign_id, lock=True)
    permission_checker.require(principal, _RESOURCE, "edit", resource_org_id=campaign.org_id)
    if campaign.status not in lifecycle.DELETABLE_STATES:
        raise CampaignNotEditableError()
    campaign.deleted_at = _now()
    campaign.version += 1
    await session.flush()
    await write_audit(
        session,
        action="advertising.campaign_deleted",
        resource_type="ad_campaign",
        resource_id=campaign.id,
        context=_audit_ctx(principal, ctx),
        before={"status": campaign.status},
    )
    await session.commit()


# --------------------------------------------------------------------------- #
# Reads                                                                       #
# --------------------------------------------------------------------------- #


async def get_campaign(
    session: AsyncSession,
    *,
    principal: Principal,
    campaign_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    campaign = await _load_owned(session, principal=principal, campaign_id=campaign_id)
    permission_checker.require(principal, _RESOURCE, "view", resource_org_id=campaign.org_id)
    return await _present(session, campaign, locale=locale)


async def list_my_campaigns(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int]:
    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "view", resource_org_id=principal.org_id)
    page_limit = clamp_limit(limit)
    stmt = select(AdCampaign).where(
        AdCampaign.org_id == principal.org_id, AdCampaign.deleted_at.is_(None)
    )
    if status is not None:
        stmt = stmt.where(AdCampaign.status == status)
    decoded = decode_cursor(cursor)
    if decoded is not None:
        anchor_created = datetime.fromisoformat(decoded["created_at"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                AdCampaign.created_at < anchor_created,
                (AdCampaign.created_at == anchor_created) & (AdCampaign.id < anchor_id),
            )
        )
    stmt = stmt.order_by(AdCampaign.created_at.desc(), AdCampaign.id.desc()).limit(page_limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda c: {"created_at": c.created_at.isoformat(), "id": str(c.id)},
    )
    items = [await _present(session, c, locale=locale) for c in page.items]
    return items, page.next_cursor, page.limit

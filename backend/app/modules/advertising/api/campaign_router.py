"""Campaign allocation-engine HTTP routes (spec §7.0).

Routers are HTTP-only: validate, delegate to services (which enforce RBAC + audit +
tenant isolation + transactions), and shape the response envelope. Three routers are
exported and mounted by the app:

- ``campaign_router`` (``/advertising``) — the partner advertiser campaign surface
  PLUS two PUBLIC (guest-allowed) endpoints: the surface allocation read and the
  privacy-safe delivery-event write. The public projections never leak
  budget/spend/targeting/org internals — only the banner + non-removable disclosure.
- ``campaign_admin_router`` (``/admin/advertising``) — university oversight of the
  campaign queue, approve/reject/pay/pause/disable/relabel, and the allocation plan.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.advertising.api.campaign_schemas import (
    CampaignApproveRequest,
    CampaignCreateRequest,
    CampaignDisclosureClassRequest,
    CampaignMarkPaidRequest,
    CampaignReasonRequest,
    CampaignRejectRequest,
    CampaignSubmitRequest,
    CampaignUpdateRequest,
    CampaignVersionRequest,
    DeliveryEventRequest,
)
from app.modules.advertising.application import (
    allocation_service,
    campaign_moderation_service,
    campaign_reporting,
    campaign_service,
)
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.discovery.application import session_service
from app.shared.responses import paginated, success

campaign_router = APIRouter(prefix="/advertising", tags=["advertising-campaigns"])
campaign_admin_router = APIRouter(
    prefix="/admin/advertising", tags=["advertising-campaigns-admin"]
)


# --------------------------------------------------------------------------- #
# Public: sponsored-slot inventory (surfaces + slots)                          #
# --------------------------------------------------------------------------- #


@campaign_router.get("/surfaces", summary="Sponsored-slot inventory per surface")
async def list_surfaces(session: AsyncSession = Depends(get_db_session)) -> dict:
    from sqlalchemy import select

    from app.modules.advertising.api import campaign_presenters
    from app.modules.advertising.domain import ad_slots as slots_vocab
    from app.modules.advertising.domain.models import AdSlot

    rows = list(
        (
            await session.execute(
                select(AdSlot).where(AdSlot.is_active.is_(True)).order_by(AdSlot.surface.asc())
            )
        ).scalars().all()
    )
    surfaces = sorted(slots_vocab.SURFACES)
    return success(
        [campaign_presenters.slot(s) for s in rows], meta={"surfaces": surfaces}
    )


# --------------------------------------------------------------------------- #
# Public: surface allocation (guest-allowed; coarse, privacy-safe)             #
# --------------------------------------------------------------------------- #


@campaign_router.get(
    "/allocations",
    summary="Filled sponsored slots for a surface + coarse viewer segment",
)
async def get_allocation(
    session: AsyncSession = Depends(get_db_session),
    surface: str = Query(...),
    location: list[str] | None = Query(default=None),
    major: list[str] | None = Query(default=None),
    career: list[str] | None = Query(default=None),
    work_mode: str | None = Query(default=None),
    cohort: str | None = Query(default=None),
    device: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    locale: str = Query(default="vi"),
) -> dict:
    """Public: return the sponsored inventory filling ``surface``'s paid slots.

    Coarse viewer signals come from explicit query params AND (optionally) a guest
    discovery session's allowlisted ``coarse_tags``. Everything is sanitized
    default-deny in the service — a forbidden/sensitive signal can never reach the
    engine. Organic/recommended inventory is NOT returned here (separate path).
    """

    signals: dict[str, object] = {
        "locations": location or [],
        "majors": major or [],
        "careers": career or [],
        "work_modes": [work_mode] if work_mode else [],
        "year_cohorts": [cohort] if cohort else [],
        "device_classes": [device] if device else [],
    }
    # Merge the guest session's coarse tags (privacy-safe; read-only).
    if session_id:
        try:
            tags = await session_service.get_coarse_tags(session, cookie_id=session_id)
        except Exception:  # noqa: BLE001 — a session read failure must not break serving
            tags = {}
        for key, value in tags.items():
            signals.setdefault(key, value)

    data = await allocation_service.allocate_surface(
        session, surface=surface, viewer_signals=signals, locale=locale
    )
    return success(data)


@campaign_router.post("/events", summary="Record a privacy-safe delivery event")
async def record_event(
    body: DeliveryEventRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await allocation_service.record_delivery_event(
        session,
        campaign_id=body.campaign_id,
        slot_code=body.slot_code,
        event_type=body.event_type,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Partner advertiser campaign surface                                          #
# --------------------------------------------------------------------------- #


@campaign_router.get("/campaigns", summary="My org's campaigns (any status)")
async def list_campaigns(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    campaign_status: str | None = Query(default=None, alias="status"),
) -> dict:
    items, next_cursor, page_limit = await campaign_service.list_my_campaigns(
        session,
        principal=auth.principal,
        status=campaign_status,
        cursor=cursor,
        limit=limit,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@campaign_router.post(
    "/campaigns",
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft campaign",
)
async def create_campaign(
    body: CampaignCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_service.create_campaign(
        session,
        principal=auth.principal,
        payload=body.model_dump(),
        ctx=auth.ctx,
    )
    return success(data)


@campaign_router.get("/campaigns/{campaign_id}", summary="Campaign detail (owner / 404)")
async def get_campaign(
    campaign_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_service.get_campaign(
        session, principal=auth.principal, campaign_id=campaign_id
    )
    return success(data)


@campaign_router.patch("/campaigns/{campaign_id}", summary="Edit a draft/rejected campaign")
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_service.update_campaign(
        session,
        principal=auth.principal,
        campaign_id=campaign_id,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


@campaign_router.post("/campaigns/{campaign_id}/submit", summary="Submit for review")
async def submit_campaign(
    campaign_id: uuid.UUID,
    body: CampaignSubmitRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_service.submit_campaign(
        session,
        principal=auth.principal,
        campaign_id=campaign_id,
        ctx=auth.ctx,
        version=body.version if body else None,
        disclosure_confirmed=body.disclosure_confirmed if body else None,
    )
    return success(data)


@campaign_router.post("/campaigns/{campaign_id}/pause", summary="Pause my campaign")
async def pause_campaign(
    campaign_id: uuid.UUID,
    body: CampaignVersionRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_service.pause_campaign(
        session,
        principal=auth.principal,
        campaign_id=campaign_id,
        ctx=auth.ctx,
        version=body.version if body else None,
    )
    return success(data)


@campaign_router.post("/campaigns/{campaign_id}/resume", summary="Resume my campaign")
async def resume_campaign(
    campaign_id: uuid.UUID,
    body: CampaignVersionRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_service.resume_campaign(
        session,
        principal=auth.principal,
        campaign_id=campaign_id,
        ctx=auth.ctx,
        version=body.version if body else None,
    )
    return success(data)


@campaign_router.post("/campaigns/{campaign_id}/end", summary="End my campaign")
async def end_campaign(
    campaign_id: uuid.UUID,
    body: CampaignVersionRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_service.end_campaign(
        session,
        principal=auth.principal,
        campaign_id=campaign_id,
        ctx=auth.ctx,
        version=body.version if body else None,
    )
    return success(data)


@campaign_router.delete("/campaigns/{campaign_id}", summary="Soft-delete a draft/rejected")
async def delete_campaign(
    campaign_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await campaign_service.delete_campaign(
        session, principal=auth.principal, campaign_id=campaign_id, ctx=auth.ctx
    )
    return success({"status": "deleted"})


@campaign_router.get(
    "/campaigns/{campaign_id}/performance",
    summary="My campaign's aggregate performance",
)
async def campaign_performance(
    campaign_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    # Ownership + RBAC via get_campaign (404 on cross-org), then the aggregate.
    await campaign_service.get_campaign(
        session, principal=auth.principal, campaign_id=campaign_id
    )
    perf = await campaign_reporting.campaign_performance(session, campaign_id=campaign_id)
    return success(perf)


# --------------------------------------------------------------------------- #
# University / admin oversight                                                #
# --------------------------------------------------------------------------- #


@campaign_admin_router.get("/campaigns", summary="Campaign review queue + spend roll-up")
async def list_review_queue(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    campaign_status: str | None = Query(default=None, alias="status"),
    org_id: uuid.UUID | None = Query(default=None),
    limit: int | None = Query(default=None),
) -> dict:
    items, total, spend = await campaign_moderation_service.list_review_queue(
        session,
        principal=auth.principal,
        status=campaign_status,
        org_id=org_id,
        limit=limit,
    )
    return success(items, meta={"count": total, "spend": spend})


@campaign_admin_router.post("/campaigns/{campaign_id}/approve", summary="Approve a campaign")
async def approve_campaign(
    campaign_id: uuid.UUID,
    body: CampaignApproveRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_moderation_service.approve_campaign(
        session,
        principal=auth.principal,
        campaign_id=campaign_id,
        note=body.note if body else None,
        version=body.version if body else None,
        ctx=auth.ctx,
    )
    return success(data)


@campaign_admin_router.post("/campaigns/{campaign_id}/reject", summary="Reject a campaign")
async def reject_campaign(
    campaign_id: uuid.UUID,
    body: CampaignRejectRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_moderation_service.reject_campaign(
        session,
        principal=auth.principal,
        campaign_id=campaign_id,
        reason=body.reason,
        reason_code=body.reason_code,
        version=body.version,
        ctx=auth.ctx,
    )
    return success(data)


@campaign_admin_router.post(
    "/campaigns/{campaign_id}/mark-paid",
    summary="Record manual/bank-transfer payment",
)
async def mark_paid(
    campaign_id: uuid.UUID,
    body: CampaignMarkPaidRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_moderation_service.mark_paid(
        session,
        principal=auth.principal,
        campaign_id=campaign_id,
        payment_reference=body.payment_reference,
        version=body.version,
        ctx=auth.ctx,
    )
    return success(data)


@campaign_admin_router.post("/campaigns/{campaign_id}/pause", summary="Pause any campaign")
async def admin_pause(
    campaign_id: uuid.UUID,
    body: CampaignReasonRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_moderation_service.admin_pause(
        session,
        principal=auth.principal,
        campaign_id=campaign_id,
        reason=body.reason if body else None,
        version=body.version if body else None,
        ctx=auth.ctx,
    )
    return success(data)


@campaign_admin_router.post("/campaigns/{campaign_id}/disable", summary="Disable any campaign")
async def admin_disable(
    campaign_id: uuid.UUID,
    body: CampaignReasonRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_moderation_service.admin_disable(
        session,
        principal=auth.principal,
        campaign_id=campaign_id,
        reason=body.reason if body else None,
        version=body.version if body else None,
        ctx=auth.ctx,
    )
    return success(data)


@campaign_admin_router.post(
    "/campaigns/{campaign_id}/disclosure-class",
    summary="Relabel a campaign's public inventory class",
)
async def set_disclosure_class(
    campaign_id: uuid.UUID,
    body: CampaignDisclosureClassRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await campaign_moderation_service.set_disclosure_class(
        session,
        principal=auth.principal,
        campaign_id=campaign_id,
        disclosure_class=body.disclosure_class,
        version=body.version,
        ctx=auth.ctx,
    )
    return success(data)


@campaign_admin_router.get("/allocations", summary="Live allocation plan (oversight)")
async def list_allocations(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    surface: str | None = Query(default=None),
    limit: int | None = Query(default=None),
) -> dict:
    items = await campaign_moderation_service.list_allocations(
        session, principal=auth.principal, surface=surface, limit=limit
    )
    return success(items, meta={"count": len(items)})

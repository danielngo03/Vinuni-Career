"""HTTP surface for the AI energy WRITE path (partner AI overhaul).

Two routers, both auth-gated (RBAC + audit + tenant isolation live in
``app.ai.energy.admin_service``, never here — routers do HTTP only):

Admin (``/organizations/ai-energy``, management / finance gated):
  GET  /organizations/ai-energy/overview              Org pool + dept/member allocations
  PUT  /organizations/ai-energy/allocations           Set/clear a dept/member weekly sub-cap
  POST /organizations/ai-energy/wallet-grants          Grant goodwill wallet to a scope
  GET  /organizations/ai-energy/topups                 List the org's top-ups
  POST /organizations/ai-energy/topups/{id}/confirm    Finance confirms money received

Member self-service (``/ai/energy``):
  POST /ai/energy/topup                                Request a top-up (pending + bank ref)
  GET  /ai/energy/topups                               My top-ups
  GET  /ai/energy/topups/{id}                          One of my top-ups

Never exposes tokens/USD/provider/model — energy is an abstract credit.
``price_amount``/``currency`` on a top-up are a real product price (VND).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.energy import admin_service
from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.shared.responses import success

admin_router = APIRouter(prefix="/organizations/ai-energy", tags=["ai-energy"])
member_router = APIRouter(prefix="/ai/energy", tags=["ai-energy"])


# --------------------------------------------------------------------------- #
# Request bodies                                                               #
# --------------------------------------------------------------------------- #


class SetAllocationBody(BaseModel):
    scope_type: str  # "department" | "user"
    scope_id: uuid.UUID
    # None clears the sub-cap → the scope shares the org pool again.
    weekly_allowance_units: int | None = Field(default=None, ge=0)


class GrantWalletBody(BaseModel):
    scope_type: str  # "org" | "department" | "user"
    scope_id: uuid.UUID
    units: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=200)


class ConfirmTopupBody(BaseModel):
    payment_reference: str = Field(min_length=1, max_length=120)


class RequestTopupBody(BaseModel):
    pack_code: str
    scope_type: str = "user"  # "user" | "department" | "org"
    scope_id: uuid.UUID | None = None


# --------------------------------------------------------------------------- #
# Admin surface                                                                #
# --------------------------------------------------------------------------- #


@admin_router.get("/overview", summary="Org AI energy pool + department/member allocations")
async def get_overview(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_service.get_org_energy_overview(session, principal=auth.principal)
    return success(data)


@admin_router.put("/allocations", summary="Set/clear a department/member weekly sub-cap")
async def set_allocation(
    body: SetAllocationBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_service.set_allocation(
        session,
        principal=auth.principal,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        weekly_allowance_units=body.weekly_allowance_units,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post("/wallet-grants", summary="Grant goodwill AI energy wallet to a scope")
async def grant_wallet(
    body: GrantWalletBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_service.grant_wallet(
        session,
        principal=auth.principal,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        units=body.units,
        reason=body.reason,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.get("/topups", summary="List my org's AI energy top-ups")
async def list_org_topups(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=None, ge=1, le=100),
) -> dict:
    data = await admin_service.list_org_topups(
        session, principal=auth.principal, status=status_filter, limit=limit
    )
    return success(data)


@admin_router.post(
    "/topups/{topup_id}/confirm",
    summary="Finance confirms a bank-transfer top-up (credits the scope wallet)",
)
async def confirm_topup(
    topup_id: uuid.UUID,
    body: ConfirmTopupBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_service.confirm_topup(
        session,
        principal=auth.principal,
        topup_id=topup_id,
        payment_reference=body.payment_reference,
        ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Member self-service surface                                                  #
# --------------------------------------------------------------------------- #


@member_router.post(
    "/topup",
    status_code=status.HTTP_201_CREATED,
    summary="Request an AI energy top-up (-> pending, bank-transfer instructions)",
)
async def request_topup(
    body: RequestTopupBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_service.request_topup(
        session,
        principal=auth.principal,
        pack_code=body.pack_code,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        ctx=auth.ctx,
    )
    return success(data)


@member_router.get("/topups", summary="My AI energy top-ups")
async def list_my_topups(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    limit: int | None = Query(default=None, ge=1, le=100),
) -> dict:
    data = await admin_service.list_my_topups(
        session, principal=auth.principal, limit=limit
    )
    return success(data)


@member_router.get("/topups/{topup_id}", summary="One of my AI energy top-ups")
async def get_my_topup(
    topup_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_service.get_topup(
        session, principal=auth.principal, topup_id=topup_id
    )
    return success(data)

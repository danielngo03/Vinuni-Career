"""Billing HTTP routes (ADR-0010 §7).

Routers are HTTP-only: validate, delegate to services (which enforce RBAC + audit
+ principal isolation + transactions), and shape the response envelope. Two routers
are exported and mounted by the app: ``router`` (the self-service subscriber
surface under ``/billing``) and ``admin_router`` (the university revenue/payment
oversight surface under ``/admin/billing``). Public sees nothing — every route is
auth-gated.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.billing.api.schemas import (
    AdminCancelRequest,
    MarkPaidRequest,
    PlanCreateRequest,
    PlanUpdateRequest,
    SubscriptionCancelRequest,
    SubscriptionRequest,
)
from app.modules.billing.application import moderation_service, subscription_service
from app.shared.responses import success

router = APIRouter(prefix="/billing", tags=["billing"])
admin_router = APIRouter(prefix="/admin/billing", tags=["billing-admin"])


# --------------------------------------------------------------------------- #
# Self-service subscriber surface                                             #
# --------------------------------------------------------------------------- #


@router.get("/plans", summary="Subscription plans for my audience")
async def list_plans(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    audience: str | None = Query(default=None),
) -> dict:
    data = await subscription_service.list_plans(
        session,
        principal=auth.principal,
        audience=audience,
    )
    return success(data)


@router.get("/subscription", summary="My current subscription + effective limits")
async def get_my_subscription(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await subscription_service.get_mine(session, principal=auth.principal)
    return success(data)


@router.post(
    "/subscription",
    status_code=status.HTTP_201_CREATED,
    summary="Request a paid plan (-> pending, bank-transfer instructions)",
)
async def request_subscription(
    body: SubscriptionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await subscription_service.request_subscription(
        session,
        principal=auth.principal,
        plan_id=body.plan_id,
        ctx=auth.ctx,
    )
    return success(data)


@router.post("/subscription/cancel", summary="Cancel my pending/active subscription")
async def cancel_subscription(
    body: SubscriptionCancelRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    version = body.version if body else None
    data = await subscription_service.cancel(
        session,
        principal=auth.principal,
        ctx=auth.ctx,
        version=version,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# University / admin oversight                                                #
# --------------------------------------------------------------------------- #


@admin_router.get("/plans", summary="All subscription plans (admin catalogue)")
async def list_admin_plans(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    audience: str | None = Query(default=None),
) -> dict:
    data = await moderation_service.list_plans_admin(
        session,
        principal=auth.principal,
        audience=audience,
    )
    return success(data)


@admin_router.post(
    "/plans",
    status_code=status.HTTP_201_CREATED,
    summary="Create a subscription plan",
)
async def create_plan(
    body: PlanCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await moderation_service.create_plan(
        session,
        principal=auth.principal,
        payload=body.model_dump(),
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.patch("/plans/{plan_id}", summary="Update a subscription plan")
async def update_plan(
    plan_id: uuid.UUID,
    body: PlanUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await moderation_service.update_plan(
        session,
        principal=auth.principal,
        plan_id=plan_id,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.get("/subscriptions", summary="All subscriptions + revenue roll-up")
async def list_all_subscriptions(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    subscription_status: str | None = Query(default=None, alias="status"),
    audience: str | None = Query(default=None),
    principal_id: uuid.UUID | None = Query(default=None),
    limit: int | None = Query(default=None),
) -> dict:
    items, total, revenue = await moderation_service.list_all(
        session,
        principal=auth.principal,
        status=subscription_status,
        audience=audience,
        principal_id=principal_id,
        limit=limit,
    )
    return success(items, meta={"count": total, "revenue": revenue})


@admin_router.post(
    "/subscriptions/{subscription_id}/mark-paid",
    summary="Record manual/bank-transfer payment -> active",
)
async def mark_paid(
    subscription_id: uuid.UUID,
    body: MarkPaidRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await moderation_service.mark_paid(
        session,
        principal=auth.principal,
        subscription_id=subscription_id,
        payment_reference=body.payment_reference,
        version=body.version,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post(
    "/subscriptions/{subscription_id}/cancel",
    summary="Admin revoke/reject a subscription",
)
async def admin_cancel(
    subscription_id: uuid.UUID,
    body: AdminCancelRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    reason = body.reason if body else None
    version = body.version if body else None
    data = await moderation_service.admin_cancel(
        session,
        principal=auth.principal,
        subscription_id=subscription_id,
        reason=reason,
        version=version,
        ctx=auth.ctx,
    )
    return success(data)

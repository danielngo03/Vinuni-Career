"""Self-service subscriber surface: plan catalog, current subscription, request,
and cancel (ADR-0010 §7).

RBAC is enforced here (not in routers) via ``PermissionChecker``: students hold
``billing:view|subscribe`` (own user-scoped subscription); partner Admins hold the
same against their own org. A subscription is keyed to the caller's principal —
either the user (student, ``org_id`` unset) or the org (partner, ``org_id`` set) —
so a caller only ever sees / mutates its own subscription, and a cross-principal
(or unknown) access returns ``404``. The chosen plan's ``price_amount`` /
``billing_period`` are frozen onto the row at request (price freeze). Every write
records an audit row in the caller's transaction.

Gates (ADR-0010 §2):
- ``request`` is rejected ``409 subscription_exists`` if a pending/active row
  already exists for the principal (the partial-unique ``uq_subscription_inflight``
  invariant; enforced in-service for the SQLite test path).
- ``request`` is rejected ``422 plan_audience_mismatch`` when ``plan.audience``
  does not match the principal kind (student->user / partner->org).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.billing.api import presenters
from app.modules.billing.application import limit_facade
from app.modules.billing.application.errors import (
    IllegalSubscriptionTransitionError,
    InvalidPlanError,
    PlanAudienceMismatchError,
    SubscriptionExistsError,
    SubscriptionVersionConflictError,
)
from app.modules.billing.domain import lifecycle
from app.modules.billing.domain.models import Subscription, SubscriptionPlan
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "billing"

# Static manual/bank-transfer instructions surfaced to the requester on a pending
# subscription (V1 = manual billing; no gateway). PII-safe, non-sensitive copy.
_PAYMENT_INSTRUCTIONS: dict[str, str] = {
    "method": "bank_transfer",
    "bank_name": "Vietcombank",
    "account_name": "VINUNI CAREER CENTER",
    "account_number": "0123456789",
    "note_hint": "VINUNI-BILLING",
}


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


def _principal_key(principal: Principal) -> tuple[str, uuid.UUID]:
    """``(principal_type, principal_id)`` for the caller; raises 404 if anonymous."""

    if principal.org_id is not None:
        return (lifecycle.PRINCIPAL_ORG, principal.org_id)
    if principal.user_id is not None:
        return (lifecycle.PRINCIPAL_USER, principal.user_id)
    raise ResourceNotFoundError()


# --------------------------------------------------------------------------- #
# Plans (catalog)                                                             #
# --------------------------------------------------------------------------- #


async def list_plans(
    session: AsyncSession,
    *,
    principal: Principal,
    audience: str | None = None,
    locale: str = "vi",
) -> list[dict]:
    """Visible plans (optionally scoped to ``audience``) + what each grants."""

    permission_checker.require(principal, _RESOURCE, "view")
    stmt = select(SubscriptionPlan).where(SubscriptionPlan.is_visible.is_(True))
    if audience is not None:
        if audience not in lifecycle.AUDIENCES:
            return []
        stmt = stmt.where(SubscriptionPlan.audience == audience)
    stmt = stmt.order_by(
        SubscriptionPlan.audience.asc(), SubscriptionPlan.sort_order.asc(),
        SubscriptionPlan.price_amount.asc(),
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [presenters.plan(p, locale=locale) for p in rows]


async def _load_plan(
    session: AsyncSession, plan_id: uuid.UUID
) -> SubscriptionPlan | None:
    return (
        await session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        )
    ).scalar_one_or_none()


async def _default_plan_for(
    session: AsyncSession, *, audience: str
) -> SubscriptionPlan | None:
    return (
        await session.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.audience == audience,
                SubscriptionPlan.is_default.is_(True),
            )
        )
    ).scalars().first()


# --------------------------------------------------------------------------- #
# Loading the caller's subscription                                           #
# --------------------------------------------------------------------------- #


async def _load_current_inflight(
    session: AsyncSession, *, principal: Principal, lock: bool = False
) -> Subscription | None:
    principal_type, principal_id = _principal_key(principal)
    stmt = select(Subscription).where(
        Subscription.principal_type == principal_type,
        Subscription.principal_id == principal_id,
        Subscription.deleted_at.is_(None),
        Subscription.status.in_(list(lifecycle.IN_FLIGHT_STATES)),
    )
    if lock and _use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalars().first()


async def _load_owned(
    session: AsyncSession,
    *,
    principal: Principal,
    subscription_id: uuid.UUID,
    lock: bool = False,
) -> Subscription:
    """Load a non-deleted subscription the caller's principal owns; else ``404``."""

    principal_type, principal_id = _principal_key(principal)
    stmt = select(Subscription).where(
        Subscription.id == subscription_id,
        Subscription.deleted_at.is_(None),
    )
    if lock and _use_for_update():
        stmt = stmt.with_for_update()
    sub = (await session.execute(stmt)).scalar_one_or_none()
    if sub is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and (
        sub.principal_type != principal_type or sub.principal_id != principal_id
    ):
        # Cross-principal access is indistinguishable from missing (404, never 403).
        raise ResourceNotFoundError()
    return sub


async def _present(
    session: AsyncSession, sub: Subscription, *, locale: str
) -> dict:
    plan_obj = await _load_plan(session, sub.plan_id)
    return presenters.subscription(sub, locale=locale, plan_obj=plan_obj)


# --------------------------------------------------------------------------- #
# Reads                                                                       #
# --------------------------------------------------------------------------- #


async def get_mine(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    """The caller's current subscription (active|pending) + effective limits.

    Null-safe: when the caller has no in-flight subscription, ``subscription`` is
    ``None`` and ``limits`` is the audience's default-plan limits map.
    """

    permission_checker.require(principal, _RESOURCE, "view")
    audience = (
        lifecycle.AUDIENCE_PARTNER if principal.org_id is not None
        else lifecycle.AUDIENCE_STUDENT
    )
    sub = await _load_current_inflight(session, principal=principal)
    default_plan = await _default_plan_for(session, audience=audience)
    effective = await limit_facade.resolve_limits(session, principal)
    if not effective and default_plan is not None:
        effective = dict(default_plan.limits or {})
    return {
        "subscription": (
            await _present(session, sub, locale=locale) if sub is not None else None
        ),
        "audience": audience,
        "limits": effective,
        "default_plan": (
            presenters.plan(default_plan, locale=locale)
            if default_plan is not None else None
        ),
    }


async def get(
    session: AsyncSession,
    *,
    principal: Principal,
    subscription_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Owner-scoped subscription detail (cross-principal -> ``404``)."""

    permission_checker.require(principal, _RESOURCE, "view")
    sub = await _load_owned(
        session, principal=principal, subscription_id=subscription_id
    )
    return await _present(session, sub, locale=locale)


# --------------------------------------------------------------------------- #
# Request (price freeze + audience match + one-inflight gate)                  #
# --------------------------------------------------------------------------- #


async def request_subscription(
    session: AsyncSession,
    *,
    principal: Principal,
    plan_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "subscribe")
    assert principal.user_id is not None
    principal_type, principal_id = _principal_key(principal)

    plan_obj = await _load_plan(session, plan_id)
    if plan_obj is None or not plan_obj.is_visible:
        raise InvalidPlanError()
    if not lifecycle.audience_matches_principal(
        plan_obj.audience, principal_type=principal_type
    ):
        raise PlanAudienceMismatchError()

    # One in-flight subscription per principal (pending|active).
    if await _load_current_inflight(session, principal=principal, lock=True):
        raise SubscriptionExistsError()

    now = _now()
    sub = Subscription(
        principal_type=principal_type,
        principal_id=principal_id,
        plan_id=plan_obj.id,
        billing_period=plan_obj.billing_period,
        price_amount=plan_obj.price_amount,  # price freeze
        currency=plan_obj.currency,
        status=lifecycle.PENDING,
        requested_by=principal.user_id,
        requested_at=now,
    )
    session.add(sub)
    await session.flush()

    await write_audit(
        session, action="billing.subscription_requested",
        resource_type="subscription", resource_id=sub.id,
        context=_audit_ctx(principal, ctx),
        after={"status": sub.status, "plan": plan_obj.code,
               "principal_type": principal_type, "price_amount": str(sub.price_amount)},
    )
    await session.commit()
    await session.refresh(sub)
    data = presenters.subscription(sub, locale=locale, plan_obj=plan_obj)
    data["payment_instructions"] = dict(_PAYMENT_INSTRUCTIONS)
    return data


# --------------------------------------------------------------------------- #
# Cancel (requester)                                                          #
# --------------------------------------------------------------------------- #


async def cancel(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    subscription_id: uuid.UUID | None = None,
    version: int | None = None,
    locale: str = "vi",
) -> dict:
    """Cancel the caller's pending|active subscription (reverts to default tier).

    With ``subscription_id`` the row must be owned by the caller (cross-principal
    -> ``404``); without it the caller's current in-flight subscription is used.
    """

    permission_checker.require(principal, _RESOURCE, "subscribe")
    if subscription_id is not None:
        sub: Subscription | None = await _load_owned(
            session, principal=principal, subscription_id=subscription_id, lock=True
        )
    else:
        sub = await _load_current_inflight(session, principal=principal, lock=True)
    if sub is None:
        raise ResourceNotFoundError()
    if version is not None and version != sub.version:
        raise SubscriptionVersionConflictError()
    if sub.status in lifecycle.TERMINAL_STATES:
        return await _present(session, sub, locale=locale)  # idempotent
    if not lifecycle.can_transition("cancel", sub.status):
        raise IllegalSubscriptionTransitionError(event="cancel")

    sub.status = lifecycle.CANCELLED
    sub.cancelled_at = _now()
    sub.cancel_reason = "cancelled_by_requester"
    sub.version += 1
    await session.flush()
    await write_audit(
        session, action="billing.subscription_cancelled",
        resource_type="subscription", resource_id=sub.id,
        context=_audit_ctx(principal, ctx),
        after={"status": sub.status, "by": "requester"},
    )
    from app.modules.billing.application import notify

    await notify.notify_owner(
        session, subscription=sub, template_key="billing.cancelled",
    )
    await session.commit()
    await session.refresh(sub)
    return await _present(session, sub, locale=locale)

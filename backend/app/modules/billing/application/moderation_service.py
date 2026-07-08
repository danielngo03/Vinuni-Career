"""University / admin billing oversight: list-all + revenue roll-up, manual
``mark_paid`` (bank-transfer), and admin cancel/revoke (ADR-0010 §5/§7).

Payment confirmation is **money received** (admin manual/bank-transfer
``mark_paid``) — the single activation gate for a subscription (there is no
separate approval state). The university-only gate mirrors
``advertising.moderation_service._require_advertising_moderator`` (superadmin OR
member of a ``university`` org holding ``billing:moderate``) so a partner Admin's
``*:*`` cannot self-confirm payment. Billing data is PII-sensitive: the revenue
roll-up + ``payment_reference`` appear only in these admin responses and audit
``after`` — never in notification bodies, never to non-admins.

RBAC + audit + tenant rules live here, not in routers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.billing.api import presenters
from app.modules.billing.application import notify
from app.modules.billing.application.errors import (
    IllegalSubscriptionTransitionError,
    PaymentReferenceRequiredError,
    SubscriptionVersionConflictError,
)
from app.modules.billing.domain import lifecycle
from app.modules.billing.domain.models import Subscription, SubscriptionPlan
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.pagination import clamp_limit
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "billing"

_PLAN_NUMERIC_LIMITS: dict[str, frozenset[str]] = {
    lifecycle.AUDIENCE_STUDENT: frozenset(
        {
            "cv_active_quota",
            "pdf_exports_per_month",
            "mass_apply_limit",
            "ai_daily_cost_quota_usd",
            "ai_weekly_energy_units",
        }
    ),
    lifecycle.AUDIENCE_PARTNER: frozenset(
        {
            "job_post_quota",
            "featured_job_slots",
            "passive_search_quota",
            "email_blast_quota",
            "ai_daily_cost_quota_usd",
            "ai_weekly_energy_units",
        }
    ),
}
_PLAN_BOOLEAN_LIMITS: dict[str, frozenset[str]] = {
    lifecycle.AUDIENCE_STUDENT: frozenset({"premium_templates"}),
    lifecycle.AUDIENCE_PARTNER: frozenset(),
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


async def _require_billing_moderator(
    session: AsyncSession, principal: Principal
) -> None:
    if principal.is_superadmin:
        return
    permission_checker.require(principal, _RESOURCE, "moderate")
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "university_only"})


def _normalize_plan_code(value: str) -> str:
    code = value.strip().lower().replace(" ", "_").replace("-", "_")
    if not code or not all(ch.isalnum() or ch == "_" for ch in code):
        raise ValidationFailedError(
            details={"field": "code", "reason": "invalid_plan_code"}
        )
    return code


def _validate_plan_vocab(audience: str, billing_period: str) -> None:
    if audience not in lifecycle.AUDIENCES:
        raise ValidationFailedError(
            details={"field": "audience", "reason": "invalid_audience"}
        )
    if billing_period not in lifecycle.BILLING_PERIODS:
        raise ValidationFailedError(
            details={"field": "billing_period", "reason": "invalid_billing_period"}
        )


def _normalize_price(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationFailedError(
            details={"field": "price_amount", "reason": "invalid_number"}
        ) from exc
    if amount < 0:
        raise ValidationFailedError(
            details={"field": "price_amount", "reason": "out_of_range"}
        )
    return amount.quantize(Decimal("0.01"))


def _normalize_limits(audience: str, raw: dict[str, Any]) -> dict[str, Any]:
    numeric = _PLAN_NUMERIC_LIMITS.get(audience, frozenset())
    boolean = _PLAN_BOOLEAN_LIMITS.get(audience, frozenset())
    allowed = numeric | boolean
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in allowed:
            raise ValidationFailedError(
                details={"field": f"limits.{key}", "reason": "unsupported_limit"}
            )
        if key in boolean:
            if not isinstance(value, bool):
                raise ValidationFailedError(
                    details={"field": f"limits.{key}", "reason": "expected_boolean"}
                )
            out[key] = value
            continue
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationFailedError(
                details={"field": f"limits.{key}", "reason": "invalid_number"}
            ) from exc
        if number < 0:
            raise ValidationFailedError(
                details={"field": f"limits.{key}", "reason": "out_of_range"}
            )
        out[key] = float(number) if "." in str(value) else int(number)
    return out


async def _ensure_single_default(
    session: AsyncSession,
    *,
    audience: str,
    keep_plan_id: uuid.UUID,
) -> None:
    rows = (
        await session.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.audience == audience,
                SubscriptionPlan.id != keep_plan_id,
                SubscriptionPlan.is_default.is_(True),
            )
        )
    ).scalars().all()
    for row in rows:
        row.is_default = False


async def _load(
    session: AsyncSession, subscription_id: uuid.UUID, *, lock: bool = False
) -> Subscription | None:
    stmt = select(Subscription).where(
        Subscription.id == subscription_id,
        Subscription.deleted_at.is_(None),
    )
    if lock and _use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def _present(
    session: AsyncSession, sub: Subscription, *, locale: str
) -> dict:
    plan_obj = (
        await session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
        )
    ).scalar_one_or_none()
    return presenters.subscription(sub, locale=locale, plan_obj=plan_obj, admin=True)


# --------------------------------------------------------------------------- #
# Plan catalogue management                                                   #
# --------------------------------------------------------------------------- #


async def list_plans_admin(
    session: AsyncSession,
    *,
    principal: Principal,
    audience: str | None = None,
    locale: str = "vi",
) -> list[dict]:
    """All plans, visible or hidden, for university billing admins."""

    await _require_billing_moderator(session, principal)
    stmt = select(SubscriptionPlan)
    if audience is not None:
        if audience not in lifecycle.AUDIENCES:
            return []
        stmt = stmt.where(SubscriptionPlan.audience == audience)
    rows = (
        await session.execute(
            stmt.order_by(
                SubscriptionPlan.audience.asc(),
                SubscriptionPlan.sort_order.asc(),
                SubscriptionPlan.price_amount.asc(),
            )
        )
    ).scalars().all()
    return [presenters.plan(row, locale=locale) for row in rows]


async def create_plan(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict[str, Any],
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Create a plan without a code deploy; audited and university-only."""

    await _require_billing_moderator(session, principal)
    code = _normalize_plan_code(str(payload["code"]))
    audience = str(payload["audience"]).strip().lower()
    billing_period = str(payload.get("billing_period") or "monthly").strip().lower()
    _validate_plan_vocab(audience, billing_period)
    exists = (
        await session.execute(
            select(SubscriptionPlan.id).where(SubscriptionPlan.code == code)
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise ValidationFailedError(
            details={"field": "code", "reason": "duplicate_plan_code"}
        )
    plan_obj = SubscriptionPlan(
        code=code,
        name=str(payload["name"]).strip(),
        name_en=str(payload["name_en"]).strip(),
        audience=audience,
        billing_period=billing_period,
        duration_days=int(payload.get("duration_days") or 30),
        price_amount=_normalize_price(payload.get("price_amount", "0")),
        currency=str(payload.get("currency") or "VND").strip().upper(),
        limits=_normalize_limits(audience, dict(payload.get("limits") or {})),
        is_default=bool(payload.get("is_default", False)),
        is_visible=bool(payload.get("is_visible", True)),
        sort_order=int(payload.get("sort_order", 0)),
    )
    session.add(plan_obj)
    await session.flush()
    if plan_obj.is_default:
        await _ensure_single_default(
            session, audience=plan_obj.audience, keep_plan_id=plan_obj.id
        )
    await write_audit(
        session,
        action="billing.plan_created",
        resource_type="subscription_plan",
        resource_id=plan_obj.id,
        context=_audit_ctx(principal, ctx),
        after={
            "code": plan_obj.code,
            "audience": plan_obj.audience,
            "limits": plan_obj.limits,
            "is_default": plan_obj.is_default,
            "is_visible": plan_obj.is_visible,
        },
    )
    await session.commit()
    await session.refresh(plan_obj)
    return presenters.plan(plan_obj, locale=locale)


async def update_plan(
    session: AsyncSession,
    *,
    principal: Principal,
    plan_id: uuid.UUID,
    payload: dict[str, Any],
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Patch an existing plan. Code/audience are immutable."""

    await _require_billing_moderator(session, principal)
    plan_obj = (
        await session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        )
    ).scalar_one_or_none()
    if plan_obj is None:
        raise ResourceNotFoundError()

    before = presenters.plan(plan_obj, locale=locale)

    if "billing_period" in payload and payload["billing_period"] is not None:
        billing_period = str(payload["billing_period"]).strip().lower()
        _validate_plan_vocab(plan_obj.audience, billing_period)
        plan_obj.billing_period = billing_period
    if "name" in payload and payload["name"] is not None:
        plan_obj.name = str(payload["name"]).strip()
    if "name_en" in payload and payload["name_en"] is not None:
        plan_obj.name_en = str(payload["name_en"]).strip()
    if "duration_days" in payload and payload["duration_days"] is not None:
        plan_obj.duration_days = int(payload["duration_days"])
    if "price_amount" in payload and payload["price_amount"] is not None:
        plan_obj.price_amount = _normalize_price(payload["price_amount"])
    if "currency" in payload and payload["currency"] is not None:
        plan_obj.currency = str(payload["currency"]).strip().upper()
    if "limits" in payload and payload["limits"] is not None:
        plan_obj.limits = _normalize_limits(plan_obj.audience, dict(payload["limits"]))
    if "is_default" in payload and payload["is_default"] is not None:
        plan_obj.is_default = bool(payload["is_default"])
    if "is_visible" in payload and payload["is_visible"] is not None:
        plan_obj.is_visible = bool(payload["is_visible"])
    if "sort_order" in payload and payload["sort_order"] is not None:
        plan_obj.sort_order = int(payload["sort_order"])

    await session.flush()
    if plan_obj.is_default:
        await _ensure_single_default(
            session, audience=plan_obj.audience, keep_plan_id=plan_obj.id
        )
    after = presenters.plan(plan_obj, locale=locale)
    await write_audit(
        session,
        action="billing.plan_updated",
        resource_type="subscription_plan",
        resource_id=plan_obj.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after=after,
    )
    await session.commit()
    await session.refresh(plan_obj)
    return presenters.plan(plan_obj, locale=locale)


# --------------------------------------------------------------------------- #
# Oversight list + revenue roll-up                                            #
# --------------------------------------------------------------------------- #


async def list_all(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    audience: str | None = None,
    principal_id: uuid.UUID | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], int, dict]:
    """All subscriptions (filterable) + a revenue roll-up (admin only)."""

    await _require_billing_moderator(session, principal)
    page_limit = clamp_limit(limit)
    base_filters: list = [Subscription.deleted_at.is_(None)]
    if status is not None:
        base_filters.append(Subscription.status == status)
    if principal_id is not None:
        base_filters.append(Subscription.principal_id == principal_id)
    if audience is not None:
        # audience lives on the plan; join via a subquery of matching plan ids.
        plan_ids = (
            select(SubscriptionPlan.id).where(SubscriptionPlan.audience == audience)
        )
        base_filters.append(Subscription.plan_id.in_(plan_ids))

    stmt = (
        select(Subscription)
        .where(*base_filters)
        .order_by(
            Subscription.requested_at.desc().nulls_last(),
            Subscription.created_at.desc(),
        )
        .limit(page_limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(
            select(func.count()).select_from(Subscription).where(*base_filters)
        )
    ).scalar_one()

    # Revenue oversight roll-up: total frozen price of ACTIVE subscriptions.
    active_revenue = (
        await session.execute(
            select(func.coalesce(func.sum(Subscription.price_amount), 0)).where(
                Subscription.deleted_at.is_(None),
                Subscription.status == lifecycle.ACTIVE,
            )
        )
    ).scalar_one()
    active_count = (
        await session.execute(
            select(func.count()).select_from(Subscription).where(
                Subscription.deleted_at.is_(None),
                Subscription.status == lifecycle.ACTIVE,
            )
        )
    ).scalar_one()
    pending_count = (
        await session.execute(
            select(func.count()).select_from(Subscription).where(
                Subscription.deleted_at.is_(None),
                Subscription.status == lifecycle.PENDING,
            )
        )
    ).scalar_one()
    items = [await _present(session, r, locale=locale) for r in rows]
    revenue = {
        "active_revenue_amount": f"{active_revenue:.2f}",
        "currency": "VND",
        "active_count": int(active_count),
        "pending_count": int(pending_count),
    }
    return items, int(total), revenue


# --------------------------------------------------------------------------- #
# Manual payment (bank-transfer) -> activate                                  #
# --------------------------------------------------------------------------- #


async def mark_paid(
    session: AsyncSession,
    *,
    principal: Principal,
    subscription_id: uuid.UUID,
    payment_reference: str,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_billing_moderator(session, principal)
    if not payment_reference or not payment_reference.strip():
        raise PaymentReferenceRequiredError()
    sub = await _load(session, subscription_id, lock=True)
    if sub is None:
        raise ResourceNotFoundError()
    if version is not None and version != sub.version:
        raise SubscriptionVersionConflictError()
    if sub.status == lifecycle.ACTIVE:
        return await _present(session, sub, locale=locale)  # idempotent
    if not lifecycle.can_transition("mark_paid", sub.status):
        raise IllegalSubscriptionTransitionError(event="mark_paid")

    plan_obj = (
        await session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
        )
    ).scalar_one_or_none()
    duration_days = plan_obj.duration_days if plan_obj is not None else 30

    now = _now()
    sub.paid_at = sub.paid_at or now
    sub.payment_reference = payment_reference.strip()
    sub.paid_by = principal.user_id
    sub.status = lifecycle.ACTIVE
    sub.start_at = now
    sub.end_at = now + timedelta(days=duration_days)
    sub.activated_at = now
    sub.version += 1
    await session.flush()
    await write_audit(
        session, action="billing.subscription_paid",
        resource_type="subscription", resource_id=sub.id,
        context=_audit_ctx(principal, ctx),
        # Revenue/reference metadata only (admin audit); never notified.
        after={"status": sub.status, "paid": True,
               "payment_reference": sub.payment_reference,
               "price_amount": str(sub.price_amount)},
    )
    await notify.notify_owner(
        session, subscription=sub, template_key="billing.payment_recorded",
    )
    await notify.notify_owner(
        session, subscription=sub, template_key="billing.active",
    )
    await session.commit()
    await session.refresh(sub)
    return await _present(session, sub, locale=locale)


# --------------------------------------------------------------------------- #
# Admin cancel / revoke                                                       #
# --------------------------------------------------------------------------- #


async def admin_cancel(
    session: AsyncSession,
    *,
    principal: Principal,
    subscription_id: uuid.UUID,
    reason: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_billing_moderator(session, principal)
    sub = await _load(session, subscription_id, lock=True)
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
    if reason and reason.strip():
        sub.cancel_reason = reason.strip()
    else:
        sub.cancel_reason = "cancelled_by_admin"
    sub.version += 1
    await session.flush()
    await write_audit(
        session, action="billing.subscription_cancelled",
        resource_type="subscription", resource_id=sub.id,
        context=_audit_ctx(principal, ctx),
        after={"status": sub.status, "by": "university"},
    )
    await notify.notify_owner(
        session, subscription=sub, template_key="billing.cancelled",
    )
    await session.commit()
    await session.refresh(sub)
    return await _present(session, sub, locale=locale)


# --------------------------------------------------------------------------- #
# Support-console package override (ADR-0014, E36)                           #
# --------------------------------------------------------------------------- #


async def admin_override_grant(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    reason: str,
    locale: str = "vi",
) -> dict:
    """Directly grant a student ``plan_id`` as an ACTIVE subscription.

    Internal API called ONLY by ``platform_support.package_override_service``
    after ITS OWN ``support:act`` + university-org gate — this function does
    NOT re-check ``billing:moderate`` (that gate is for billing's own admin
    surface; the support-console call site is authorized under a different
    permission noun per ADR-0014 §6). Any prior in-flight (pending/active)
    subscription for the user is superseded (cancelled) so the override is
    unambiguous. Bypasses the manual bank-transfer step (`mark_paid`) — this
    IS the payment-bypass admin action, audited as such by the caller.
    """

    plan = await _load_plan_any(session, plan_id)
    if plan is None or plan.audience != lifecycle.AUDIENCE_STUDENT:
        raise ValidationFailedError(details={"field": "plan_id"})

    existing = (
        await session.execute(
            select(Subscription).where(
                Subscription.principal_type == lifecycle.PRINCIPAL_USER,
                Subscription.principal_id == user_id,
                Subscription.status.in_(lifecycle.IN_FLIGHT_STATES),
                Subscription.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    now = _now()
    for row in existing:
        row.status = lifecycle.CANCELLED
        row.cancelled_at = now
        row.cancel_reason = "support_override_superseded"
        row.version += 1

    sub = Subscription(
        principal_type=lifecycle.PRINCIPAL_USER,
        principal_id=user_id,
        plan_id=plan.id,
        billing_period=plan.billing_period,
        price_amount=plan.price_amount,
        currency=plan.currency,
        status=lifecycle.ACTIVE,
        start_at=now,
        end_at=now + timedelta(days=plan.duration_days),
        requested_by=user_id,
        requested_at=now,
        paid_at=now,
        payment_reference=f"support_override:{reason.strip()[:80]}",
        paid_by=principal.user_id,
        activated_at=now,
    )
    session.add(sub)
    await session.flush()
    await write_audit(
        session,
        action="billing.subscription_support_overridden",
        resource_type="subscription",
        resource_id=sub.id,
        context=_audit_ctx(principal, ctx),
        after={"status": sub.status, "plan_id": str(plan.id), "user_id": str(user_id)},
    )
    return await _present(session, sub, locale=locale)


async def _load_plan_any(
    session: AsyncSession, plan_id: uuid.UUID
) -> SubscriptionPlan | None:
    return (
        await session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        )
    ).scalar_one_or_none()

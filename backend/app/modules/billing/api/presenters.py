"""ORM -> friendly response shapes for billing (ADR-0010 §7).

Presenters emit vi+en labels (``status_label``, ``audience_label``,
``billing_period_label``), the frozen price + currency, the window, and the plan's
human-readable grants — **never raw enum codes alone, never another principal's
data, and never the bank-transfer ``payment_reference`` to a non-admin**. The
``payment_reference`` is admin-only spend oversight (``admin=True``).
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.billing.domain import lifecycle
from app.modules.billing.domain.models import Subscription, SubscriptionPlan


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _amount(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def plan(p: SubscriptionPlan, *, locale: str = "vi") -> dict:
    return {
        "id": str(p.id),
        "code": p.code,
        "name": p.name if locale == "vi" else p.name_en,
        "name_vi": p.name,
        "name_en": p.name_en,
        "audience": p.audience,
        "audience_label": lifecycle.audience_label(p.audience, locale=locale),
        "billing_period": p.billing_period,
        "billing_period_label": lifecycle.billing_period_label(
            p.billing_period, locale=locale
        ),
        "duration_days": p.duration_days,
        "price_amount": _amount(p.price_amount),
        "currency": p.currency,
        "limits": dict(p.limits or {}),
        "is_default": p.is_default,
        "is_visible": p.is_visible,
        "sort_order": p.sort_order,
    }


def subscription(
    s: Subscription,
    *,
    locale: str = "vi",
    plan_obj: SubscriptionPlan | None = None,
    admin: bool = False,
) -> dict:
    data = {
        "id": str(s.id),
        "principal_type": s.principal_type,
        "plan_id": str(s.plan_id),
        "plan": plan(plan_obj, locale=locale) if plan_obj is not None else None,
        "billing_period": s.billing_period,
        "billing_period_label": lifecycle.billing_period_label(
            s.billing_period, locale=locale
        ),
        "price_amount": _amount(s.price_amount),
        "currency": s.currency,
        "status": s.status,
        "status_label": lifecycle.status_label(s.status, locale=locale),
        "start_at": _iso(s.start_at),
        "end_at": _iso(s.end_at),
        "is_paid": s.paid_at is not None,
        "paid_at": _iso(s.paid_at),
        "requested_at": _iso(s.requested_at),
        "activated_at": _iso(s.activated_at),
        "expired_at": _iso(s.expired_at),
        "cancelled_at": _iso(s.cancelled_at),
        "created_at": _iso(s.created_at),
        "updated_at": _iso(s.updated_at),
        "version": s.version,
    }
    if admin:
        # Spend oversight: the bank-transfer reference + principal id are admin-only.
        data["principal_id"] = str(s.principal_id)
        data["payment_reference"] = s.payment_reference
        data["requested_by"] = str(s.requested_by)
        data["paid_by"] = str(s.paid_by) if s.paid_by else None
        data["cancel_reason"] = s.cancel_reason
    return data

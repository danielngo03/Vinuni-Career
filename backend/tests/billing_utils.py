"""Shared helpers for billing / subscription tests (ADR-0010)."""

from __future__ import annotations

from decimal import Decimal

from app.modules.billing.domain.models import SubscriptionPlan
from sqlalchemy.ext.asyncio import AsyncSession

# The four seeded reference plans (the migration data step, in-test). Limits maps
# mirror migration 0019 / ADR-0010 §1.
_SEED_PLANS: list[dict] = [
    {
        "code": "student_free", "name": "Sinh viên — Miễn phí",
        "name_en": "Student — Free", "audience": "student",
        "price_amount": "0.00", "limits": {"cv_active_quota": 5,
        "pdf_exports_per_month": 3, "premium_templates": False,
        "mass_apply_limit": 0, "ai_daily_cost_quota_usd": 0.02},
        "is_default": True, "sort_order": 0,
    },
    {
        "code": "student_pro", "name": "Sinh viên — Pro",
        "name_en": "Student — Pro", "audience": "student",
        "price_amount": "99000.00", "limits": {"cv_active_quota": 10,
        "pdf_exports_per_month": 50, "premium_templates": True,
        "mass_apply_limit": 10, "ai_daily_cost_quota_usd": 0.75,
        "ai_weekly_energy_units": 1500},
        "is_default": False, "sort_order": 1,
    },
    {
        "code": "partner_basic", "name": "Đối tác — Cơ bản",
        "name_en": "Partner — Basic", "audience": "partner",
        "price_amount": "0.00", "limits": {"job_post_quota": 5,
        "featured_job_slots": 0, "passive_search_quota": 0,
        "email_blast_quota": 0, "ai_daily_cost_quota_usd": 0.05,
        "ai_weekly_energy_units": 400},
        "is_default": True, "sort_order": 0,
    },
    {
        "code": "partner_pro", "name": "Đối tác — Pro",
        "name_en": "Partner — Pro", "audience": "partner",
        "price_amount": "2000000.00", "limits": {"job_post_quota": 20,
        "featured_job_slots": 3, "passive_search_quota": 50,
        "email_blast_quota": 10, "ai_daily_cost_quota_usd": 1.50,
        "ai_weekly_energy_units": 1500},
        "is_default": False, "sort_order": 1,
    },
]


async def seed_plans(db: AsyncSession) -> dict[str, SubscriptionPlan]:
    """Seed the four reference plans and return them keyed by ``code``."""

    out: dict[str, SubscriptionPlan] = {}
    for spec in _SEED_PLANS:
        plan = SubscriptionPlan(
            code=spec["code"], name=spec["name"], name_en=spec["name_en"],
            audience=spec["audience"], billing_period="monthly", duration_days=30,
            price_amount=Decimal(spec["price_amount"]), currency="VND",
            limits=spec["limits"], is_default=spec["is_default"],
            is_visible=True, sort_order=spec["sort_order"],
        )
        db.add(plan)
        out[spec["code"]] = plan
    await db.commit()
    for plan in out.values():
        await db.refresh(plan)
    return out

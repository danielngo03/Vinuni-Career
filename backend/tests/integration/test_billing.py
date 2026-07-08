"""Subscriptions & manual-billing service tests (ADR-0010 first slice).

Covers the plan/subscription lifecycle + manual mark_paid + the CV-quota
limit-resolution seam end to end: plan list; request -> pending -> mark_paid ->
active (window set, price frozen, bank-ref recorded); the CV-quota override (a
student on student_pro may create a 6th active CV; with no subscription the default
5 holds); expiry reverts the cap to 5; one in-flight -> 409; audience mismatch ->
422; cross-principal -> 404; university-only mark_paid (partner *:* -> 403); the
revenue roll-up; the expiry sweep via the scheduler tick (idempotent); audit per
write; PII-safety (no payment_reference / revenue in notification bodies); and the
cross-module rule (billing never imports the documents ORM; documents lazy-imports
only the billing limit facade).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.ai.energy import service as energy_service
from app.modules.automation.scheduler import runner
from app.modules.billing.application import (
    expiry_service,
    limit_facade,
    moderation_service,
    subscription_service,
)
from app.modules.billing.application.errors import (
    PlanAudienceMismatchError,
    SubscriptionExistsError,
)
from app.modules.billing.domain.models import Subscription, SubscriptionPlan
from app.modules.documents.application import cv_service
from app.modules.notifications.domain.models import NotificationOutbox
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.models import AuditLog
from app.shared.permissions import Principal
from sqlalchemy import func, select

from tests.auth_utils import CTX, register_verified
from tests.billing_utils import seed_plans
from tests.documents_utils import make_ready_cv, make_student
from tests.org_utils import make_org_with_admin

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _request_and_activate(
    db, *, subscriber, uni, plan, reference="BANK-REF-001"
) -> uuid.UUID:
    res = await subscription_service.request_subscription(
        db, principal=subscriber, plan_id=plan.id, ctx=CTX,
    )
    sub_id = uuid.UUID(res["id"])
    await moderation_service.mark_paid(
        db, principal=uni, subscription_id=sub_id,
        payment_reference=reference, ctx=CTX,
    )
    return sub_id


async def _make_blank(db, student, title: str) -> dict:
    return await cv_service.create_cv(
        db, principal=student,
        payload={"title": title, "creation_mode": "blank_template"}, ctx=CTX,
    )


# --------------------------------------------------------------------------- #
# Plans                                                                       #
# --------------------------------------------------------------------------- #


async def test_list_plans_scoped_by_audience(db_session) -> None:
    await seed_plans(db_session)
    _u, student = await make_student(db_session)
    plans = await subscription_service.list_plans(
        db_session, principal=student, audience="student",
    )
    assert {p["code"] for p in plans} == {"student_free", "student_pro"}
    pro = next(p for p in plans if p["code"] == "student_pro")
    assert pro["limits"]["cv_active_quota"] == 10
    assert pro["price_amount"] == "99000.00"
    assert pro["audience_label"] and pro["billing_period_label"]  # localized


# --------------------------------------------------------------------------- #
# Request -> pending -> mark_paid -> active                                   #
# --------------------------------------------------------------------------- #


async def test_request_then_mark_paid_activates_with_window(db_session) -> None:
    plans = await seed_plans(db_session)
    _u, student = await make_student(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")

    res = await subscription_service.request_subscription(
        db_session, principal=student, plan_id=plans["student_pro"].id, ctx=CTX,
    )
    assert res["status"] == "pending"
    assert res["price_amount"] == "99000.00"  # frozen at request
    assert res["payment_instructions"]["method"] == "bank_transfer"
    sub_id = uuid.UUID(res["id"])

    activated = await moderation_service.mark_paid(
        db_session, principal=uni, subscription_id=sub_id,
        payment_reference="BANK-REF-XYZ", ctx=CTX,
    )
    assert activated["status"] == "active"
    assert activated["start_at"] is not None and activated["end_at"] is not None
    # Admin projection carries the bank-transfer reference (spend oversight).
    assert activated["payment_reference"] == "BANK-REF-XYZ"


# --------------------------------------------------------------------------- #
# CV-quota override: student_pro -> 10; no subscription -> default 5          #
# --------------------------------------------------------------------------- #


async def test_cv_quota_override_lets_student_pro_create_sixth_cv(db_session) -> None:
    plans = await seed_plans(db_session)
    user, student = await make_student(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")

    # No subscription: the documented VinUni default of 5 holds.
    limit, source = await cv_service._resolve_active_cv_limit(
        db_session, principal=student
    )
    assert (limit, source) == (5, "student_tier")

    await _request_and_activate(
        db_session, subscriber=student, uni=uni, plan=plans["student_pro"],
    )

    # Active student_pro overrides the cap to 10 (source flips to subscription).
    limit, source = await cv_service._resolve_active_cv_limit(
        db_session, principal=student
    )
    assert (limit, source) == (10, "subscription")
    quota = await cv_service.cv_library_quota(db_session, principal=student)
    assert quota["active_cv_limit"] == 10
    assert quota["quota_source"] == "subscription"

    # The student may now COMMIT a 6th CV to their library (the default 5 would have
    # blocked finalize at the 6th). Drafts are unlimited; only finalize counts.
    for i in range(6):
        await make_ready_cv(db_session, student=student, title=f"CV {i}")
    assert await cv_service.count_cvs(db_session, principal=student) == 6


async def test_cv_quota_default_five_without_subscription(db_session) -> None:
    await seed_plans(db_session)
    _u, student = await make_student(db_session)
    quota = await cv_service.cv_library_quota(db_session, principal=student)
    assert quota["active_cv_limit"] == 5
    assert quota["quota_source"] == "student_tier"
    limit, source = await cv_service._resolve_active_cv_limit(
        db_session, principal=student
    )
    assert (limit, source) == (5, "student_tier")


async def test_vinuni_student_gets_higher_ai_quota_than_external_student(
    db_session,
) -> None:
    await seed_plans(db_session)
    vin_user = await register_verified(db_session, email="quota@vinuni.edu.vn")
    external_user = await register_verified(db_session, email="quota@example.edu")

    vinuni = Principal(
        user_id=vin_user.id,
        persona="student",
        permissions=frozenset({"billing:view"}),
    )
    external = Principal(
        user_id=external_user.id,
        persona="student",
        permissions=frozenset({"billing:view"}),
    )

    vinuni_limits = await limit_facade.resolve_limits(db_session, vinuni)
    external_limits = await limit_facade.resolve_limits(db_session, external)

    assert vinuni_limits["student_segment"] == "vinuni_student"
    assert external_limits["student_segment"] == "external_student"
    assert (
        vinuni_limits["ai_daily_cost_quota_usd"]
        > external_limits["ai_daily_cost_quota_usd"]
    )


async def test_student_pro_plan_overrides_segment_ai_quota(db_session) -> None:
    plans = await seed_plans(db_session)
    user = await register_verified(db_session, email="quota-pro@vinuni.edu.vn")
    student = Principal(
        user_id=user.id,
        persona="student",
        permissions=frozenset({"billing:view", "billing:subscribe"}),
    )
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")

    before = await limit_facade.resolve_user_ai_daily_cost_quota(
        db_session,
        user.id,
    )
    await _request_and_activate(
        db_session,
        subscriber=student,
        uni=uni,
        plan=plans["student_pro"],
    )
    after = await limit_facade.resolve_user_ai_daily_cost_quota(db_session, user.id)

    assert before == 0.20
    assert after == 0.75


# --------------------------------------------------------------------------- #
# Masked weekly AI-energy allowance (energy model) — no USD leaks to students  #
# --------------------------------------------------------------------------- #


def _student(user_id, *, perms: set[str]) -> Principal:
    return Principal(
        user_id=user_id, persona="student", permissions=frozenset(perms)
    )


async def test_student_entitlements_hide_usd_and_show_weekly_energy(
    db_session,
) -> None:
    """The self-service billing response must NOT leak a raw daily-USD figure and
    MUST carry the masked weekly AI-energy allowance (VinUni student -> 300)."""

    await seed_plans(db_session)
    vin_user = await register_verified(db_session, email="ent@vinuni.edu.vn")
    student = _student(vin_user.id, perms={"billing:view"})

    mine = await subscription_service.get_mine(db_session, principal=student)

    # (a) No USD / internal segment marker anywhere on the entitlements response.
    assert "ai_daily_cost_quota_usd" not in mine["limits"]
    assert "student_segment" not in mine["limits"]
    assert "ai_daily_cost_quota_usd" not in mine["default_plan"]["limits"]
    # (a)+(b) Masked weekly AI-energy allowance present and segment-correct.
    assert mine["limits"]["ai_weekly_energy_units"] == 300
    assert mine["default_plan"]["limits"]["ai_weekly_energy_units"] == 300


async def test_external_student_entitlements_weekly_energy_is_lower(
    db_session,
) -> None:
    await seed_plans(db_session)
    ext_user = await register_verified(db_session, email="ent@example.edu")
    student = _student(ext_user.id, perms={"billing:view"})

    mine = await subscription_service.get_mine(db_session, principal=student)

    assert "ai_daily_cost_quota_usd" not in mine["limits"]
    assert mine["limits"]["ai_weekly_energy_units"] == 120


async def test_plan_comparison_masks_usd_and_scales_weekly_energy(db_session) -> None:
    """The plan comparison table shows a masked weekly AI-energy row per plan: the
    free tier from the caller's segment, the Pro tier from its explicit value."""

    await seed_plans(db_session)
    vin_user = await register_verified(db_session, email="cmp@vinuni.edu.vn")
    ext_user = await register_verified(db_session, email="cmp@example.edu")
    vin = _student(vin_user.id, perms={"billing:view"})
    ext = _student(ext_user.id, perms={"billing:view"})

    vin_plans = await subscription_service.list_plans(
        db_session, principal=vin, audience="student"
    )
    ext_plans = await subscription_service.list_plans(
        db_session, principal=ext, audience="student"
    )

    for plans in (vin_plans, ext_plans):
        for p in plans:
            assert "ai_daily_cost_quota_usd" not in p["limits"]
            assert "student_segment" not in p["limits"]

    vin_free = next(p for p in vin_plans if p["code"] == "student_free")
    vin_pro = next(p for p in vin_plans if p["code"] == "student_pro")
    ext_free = next(p for p in ext_plans if p["code"] == "student_free")
    ext_pro = next(p for p in ext_plans if p["code"] == "student_pro")

    # Free tier scales with the viewer's segment; Pro is the explicit higher tier.
    assert vin_free["limits"]["ai_weekly_energy_units"] == 300
    assert ext_free["limits"]["ai_weekly_energy_units"] == 120
    assert vin_pro["limits"]["ai_weekly_energy_units"] == 1500
    assert ext_pro["limits"]["ai_weekly_energy_units"] == 1500


async def test_energy_meter_reflects_segment_and_pro_allowance(db_session) -> None:
    """The header energy meter (energy_service.snapshot) resolves the SAME masked
    weekly allowance billing shows: VinUni 300, external 120, active Pro 1500 — and
    never leaks USD/token internals in its public shape."""

    plans = await seed_plans(db_session)
    vin_user = await register_verified(db_session, email="meter@vinuni.edu.vn")
    ext_user = await register_verified(db_session, email="meter@example.edu")
    pro_user = await register_verified(db_session, email="meter-pro@vinuni.edu.vn")
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")

    vin = _student(vin_user.id, perms={"billing:view"})
    ext = _student(ext_user.id, perms={"billing:view"})
    pro = _student(pro_user.id, perms={"billing:view", "billing:subscribe"})

    vin_snap = await energy_service.snapshot(db_session, principal=vin)
    ext_snap = await energy_service.snapshot(db_session, principal=ext)
    assert vin_snap.weekly_allowance == 300
    assert ext_snap.weekly_allowance == 120

    await _request_and_activate(
        db_session, subscriber=pro, uni=uni, plan=plans["student_pro"]
    )
    pro_snap = await energy_service.snapshot(db_session, principal=pro)
    assert pro_snap.weekly_allowance == 1500

    # Leakage guard: the public meter shape carries only opaque energy fields.
    public = vin_snap.to_public()
    flat = str(public).lower()
    assert "usd" not in flat and "token" not in flat and "cost" not in flat


async def test_resolve_limits_keeps_usd_internally_for_budget_guard(db_session) -> None:
    """The resolver stays truthful for INTERNAL consumers (budget_guard/superadmin):
    the raw USD quota is still resolvable even though it is masked on the response."""

    await seed_plans(db_session)
    vin_user = await register_verified(db_session, email="internal@vinuni.edu.vn")
    student = _student(vin_user.id, perms={"billing:view"})

    limits = await limit_facade.resolve_limits(db_session, student)
    assert limits["ai_daily_cost_quota_usd"] == 0.20
    assert limits["ai_weekly_energy_units"] == 300
    # And the dedicated internal accessor still returns the USD quota.
    usd = await limit_facade.resolve_user_ai_daily_cost_quota(db_session, vin_user.id)
    assert usd == 0.20


async def test_university_admin_can_create_and_update_plan_limits(db_session) -> None:
    plans = await seed_plans(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")

    created = await moderation_service.create_plan(
        db_session,
        principal=uni,
        ctx=CTX,
        payload={
            "code": "student_elite",
            "name": "Sinh viên Elite",
            "name_en": "Student Elite",
            "audience": "student",
            "billing_period": "monthly",
            "duration_days": 30,
            "price_amount": "199000.00",
            "currency": "VND",
            "limits": {
                "cv_active_quota": 20,
                "premium_templates": True,
                "ai_daily_cost_quota_usd": 2.5,
            },
            "is_default": False,
            "is_visible": True,
            "sort_order": 9,
        },
    )

    assert created["code"] == "student_elite"
    assert created["limits"]["ai_daily_cost_quota_usd"] == 2.5

    updated = await moderation_service.update_plan(
        db_session,
        principal=uni,
        plan_id=uuid.UUID(created["id"]),
        ctx=CTX,
        payload={"is_default": True, "limits": {"cv_active_quota": 12}},
    )

    assert updated["is_default"] is True
    assert updated["limits"] == {"cv_active_quota": 12}
    old_default = (
        await db_session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plans["student_free"].id)
        )
    ).scalar_one()
    assert old_default.is_default is False


async def test_partner_admin_cannot_manage_plan_catalog(db_session) -> None:
    await seed_plans(db_session)
    _pu, _po, partner = await make_org_with_admin(db_session, org_type="partner")

    with pytest.raises(PermissionDeniedError):
        await moderation_service.create_plan(
            db_session,
            principal=partner,
            ctx=CTX,
            payload={
                "code": "partner_secret",
                "name": "Secret",
                "name_en": "Secret",
                "audience": "partner",
                "limits": {"job_post_quota": 999},
            },
        )


async def test_plan_limit_validation_rejects_unknown_keys(db_session) -> None:
    await seed_plans(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")

    with pytest.raises(ValidationFailedError) as exc:
        await moderation_service.create_plan(
            db_session,
            principal=uni,
            ctx=CTX,
            payload={
                "code": "student_bad",
                "name": "Bad",
                "name_en": "Bad",
                "audience": "student",
                "limits": {"drop_database": 1},
            },
        )

    assert exc.value.details["reason"] == "unsupported_limit"


async def test_expiry_reverts_cv_quota_to_default(db_session) -> None:
    plans = await seed_plans(db_session)
    user, student = await make_student(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    sub_id = await _request_and_activate(
        db_session, subscriber=student, uni=uni, plan=plans["student_pro"],
    )
    limit, _ = await cv_service._resolve_active_cv_limit(db_session, principal=student)
    assert limit == 10

    # Force the window closed and sweep -> expired -> cap reverts to default 5.
    sub = (
        await db_session.execute(select(Subscription).where(Subscription.id == sub_id))
    ).scalar_one()
    sub.end_at = _now() - timedelta(minutes=1)
    await db_session.commit()
    result = await expiry_service.expiry_sweep(db_session, now=_now())
    await db_session.commit()
    assert result["expired"] == 1

    limit, source = await cv_service._resolve_active_cv_limit(
        db_session, principal=student
    )
    assert (limit, source) == (5, "student_tier")


# --------------------------------------------------------------------------- #
# One in-flight -> 409; audience mismatch -> 422; cross-principal -> 404      #
# --------------------------------------------------------------------------- #


async def test_second_request_while_in_flight_is_409(db_session) -> None:
    plans = await seed_plans(db_session)
    _u, student = await make_student(db_session)
    await subscription_service.request_subscription(
        db_session, principal=student, plan_id=plans["student_pro"].id, ctx=CTX,
    )
    with pytest.raises(SubscriptionExistsError):
        await subscription_service.request_subscription(
            db_session, principal=student, plan_id=plans["student_pro"].id, ctx=CTX,
        )


async def test_request_wrong_audience_is_422(db_session) -> None:
    plans = await seed_plans(db_session)
    _u, student = await make_student(db_session)
    with pytest.raises(PlanAudienceMismatchError):
        await subscription_service.request_subscription(
            db_session, principal=student, plan_id=plans["partner_pro"].id, ctx=CTX,
        )


async def test_cross_principal_get_is_404(db_session) -> None:
    plans = await seed_plans(db_session)
    _ua, student_a = await make_student(db_session, prefix="a")
    _ub, student_b = await make_student(db_session, prefix="b")
    res = await subscription_service.request_subscription(
        db_session, principal=student_a, plan_id=plans["student_pro"].id, ctx=CTX,
    )
    sub_id = uuid.UUID(res["id"])
    # B may not view A's subscription — indistinguishable from missing (404).
    with pytest.raises(ResourceNotFoundError):
        await subscription_service.get(
            db_session, principal=student_b, subscription_id=sub_id,
        )


# --------------------------------------------------------------------------- #
# University-only oversight                                                   #
# --------------------------------------------------------------------------- #


async def test_partner_admin_cannot_mark_paid(db_session) -> None:
    plans = await seed_plans(db_session)
    _u, student = await make_student(db_session)
    _pu, _po, partner = await make_org_with_admin(db_session)  # partner admin *:*
    res = await subscription_service.request_subscription(
        db_session, principal=student, plan_id=plans["student_pro"].id, ctx=CTX,
    )
    sub_id = uuid.UUID(res["id"])
    # Partner admin holds *:* but org_type != university -> 403.
    with pytest.raises(PermissionDeniedError):
        await moderation_service.mark_paid(
            db_session, principal=partner, subscription_id=sub_id,
            payment_reference="REF", ctx=CTX,
        )


async def test_revenue_rollup_sums_active_frozen_prices(db_session) -> None:
    plans = await seed_plans(db_session)
    _u, student = await make_student(db_session)
    _pu, _po, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")

    await _request_and_activate(
        db_session, subscriber=student, uni=uni, plan=plans["student_pro"],
        reference="REF-STU",
    )
    await _request_and_activate(
        db_session, subscriber=partner, uni=uni, plan=plans["partner_pro"],
        reference="REF-PARTNER",
    )

    items, total, revenue = await moderation_service.list_all(
        db_session, principal=uni,
    )
    assert total == 2
    assert revenue["active_count"] == 2
    assert revenue["active_revenue_amount"] == "2099000.00"  # 99000 + 2000000
    # Admin oversight rows carry the bank-transfer reference.
    assert any(i.get("payment_reference") for i in items)


# --------------------------------------------------------------------------- #
# Expiry sweep via the scheduler tick (idempotent)                            #
# --------------------------------------------------------------------------- #


async def test_expiry_sweep_via_tick_is_idempotent(db_session) -> None:
    plans = await seed_plans(db_session)
    _u, student = await make_student(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    sub_id = await _request_and_activate(
        db_session, subscriber=student, uni=uni, plan=plans["student_pro"],
    )
    sub = (
        await db_session.execute(select(Subscription).where(Subscription.id == sub_id))
    ).scalar_one()
    sub.end_at = _now() - timedelta(minutes=1)
    await db_session.commit()

    # Run the registered scheduler job (proves the registry wiring), idempotently.
    r1 = await runner.run_job("billing.expiry_sweep", now=_now())
    assert r1 == {"expired": 1}
    r2 = await runner.run_job("billing.expiry_sweep", now=_now())
    assert r2 == {"expired": 0}


# --------------------------------------------------------------------------- #
# Audit per write                                                             #
# --------------------------------------------------------------------------- #


async def test_audit_row_per_write(db_session) -> None:
    plans = await seed_plans(db_session)
    _u, student = await make_student(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    sub_id = await _request_and_activate(
        db_session, subscriber=student, uni=uni, plan=plans["student_pro"],
    )
    await moderation_service.admin_cancel(
        db_session, principal=uni, subscription_id=sub_id, reason="policy", ctx=CTX,
    )
    assert await _audit_count(db_session, "billing.subscription_requested") == 1
    assert await _audit_count(db_session, "billing.subscription_paid") == 1
    assert await _audit_count(db_session, "billing.subscription_cancelled") == 1


# --------------------------------------------------------------------------- #
# PII safety: no payment reference / revenue in notification bodies           #
# --------------------------------------------------------------------------- #


async def test_no_payment_reference_in_notification_bodies(db_session) -> None:
    plans = await seed_plans(db_session)
    user, student = await make_student(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    secret_ref = "BANK-REF-SECRET-12345"
    await _request_and_activate(
        db_session, subscriber=student, uni=uni, plan=plans["student_pro"],
        reference=secret_ref,
    )

    # Outbox (email) rows for the owner carry only name/email — never the reference.
    outbox = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == user.id
            )
        )
    ).scalars().all()
    billing_rows = [r for r in outbox if r.template_key.startswith("billing.")]
    assert billing_rows  # at least payment_recorded + active were enqueued
    for row in billing_rows:
        assert set(row.variables.keys()) <= {"name", "email"}
        assert secret_ref not in str(row.variables)


# --------------------------------------------------------------------------- #
# Cross-module rule: billing <-> documents boundary                          #
# --------------------------------------------------------------------------- #


def test_billing_does_not_import_documents_orm() -> None:
    import ast
    import pathlib

    root = pathlib.Path("app/modules/billing")
    forbidden = "app.modules.documents"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(forbidden):
                    offenders.append(f"{path}: {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden):
                        offenders.append(f"{path}: {alias.name}")
    assert offenders == [], offenders


def test_documents_only_imports_the_billing_limit_facade() -> None:
    import ast
    import pathlib

    root = pathlib.Path("app/modules/documents")
    allowed = "app.modules.billing.application.limit_facade"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            # Resolve every imported symbol to its fully-qualified module path; the
            # ONLY billing target documents may reach is the limit-resolution facade.
            targets: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("app.modules.billing"):
                    targets = [f"{node.module}.{a.name}" for a in node.names]
                    # `import limit_facade` resolves to module.limit_facade; an
                    # `from ...limit_facade import x` has module == allowed already.
                    if node.module == allowed:
                        targets = [allowed]
            elif isinstance(node, ast.Import):
                targets = [
                    a.name for a in node.names
                    if a.name.startswith("app.modules.billing")
                ]
            offenders.extend(
                f"{path}: {t}" for t in targets if t != allowed
            )
    assert offenders == [], offenders

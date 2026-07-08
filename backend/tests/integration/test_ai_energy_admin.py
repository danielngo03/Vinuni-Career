"""AI energy WRITE path — allocation, wallet grant, and top-up purchases.

Covers (partner AI overhaul, ``app.ai.energy.admin_service`` + the member sub-cap
enforcement added to ``app.ai.energy.service``):

(a) admin sets a member weekly sub-cap → the overview + the member's snapshot
    reflect it, and the member is gated on their OWN allocation (not just the org
    pool);
(b) a member requests a top-up (pending) → finance confirms → wallet credited on
    the target scope + the member's snapshot capacity grows;
(c) confirm is idempotent (no double credit);
(d) a non-admin member cannot allocate / grant / confirm (403);
(e) cross-org allocation is denied;
(f) a member self-service top-up needs no admin capability, but requesting for a
    different scope does; an org-scope wallet grant needs finance, not management.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.ai.energy import admin_service
from app.ai.energy import service as energy_service
from app.ai.energy.models import (
    SCOPE_DEPARTMENT,
    SCOPE_ORG,
    SCOPE_USER,
    TOPUP_PAID,
    TOPUP_PENDING,
    AiEnergyAccount,
)
from app.ai.observability.billable_usage import (
    PERSONA_PARTNER,
    RESULT_SUCCESS,
)
from app.ai.observability.billable_usage import (
    SCOPE_ORG as LEDGER_SCOPE_ORG,
)
from app.ai.observability.models import AiBillableUsage
from app.modules.organization.domain.models import Department
from app.shared.exceptions import (
    PermissionDeniedError,
    QuotaExceededError,
    ValidationFailedError,
)
from app.shared.permissions import Principal
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin

SMALL_UNITS = admin_service.ENERGY_PACKS["small"]["units"]


async def _charge_member(db_session, *, org_id, user_id, units: int) -> None:
    """A partner member's metered spend: counts against BOTH the org pool
    (``org_id``) and the member's own user scope (``actor_user_id``)."""
    db_session.add(
        AiBillableUsage(
            actor_persona=PERSONA_PARTNER,
            billing_scope=LEDGER_SCOPE_ORG,
            feature_key="chatbot",
            task_type="x",
            result_status=RESULT_SUCCESS,
            units_charged=units,
            org_id=org_id,
            actor_user_id=user_id,
            created_at=datetime.now(UTC),
        )
    )
    await db_session.commit()


async def _account(db_session, scope_type, scope_id) -> AiEnergyAccount | None:
    return (
        await db_session.execute(
            select(AiEnergyAccount).where(
                AiEnergyAccount.scope_type == scope_type,
                AiEnergyAccount.scope_id == scope_id,
            )
        )
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# (a) allocation reflected + enforced                                          #
# --------------------------------------------------------------------------- #


async def test_admin_sets_member_subcap_reflected_and_enforced(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    member_user, _m, member = await add_member(
        db_session, org=org, permissions=[]
    )

    res = await admin_service.set_allocation(
        db_session,
        principal=admin,
        scope_type=SCOPE_USER,
        scope_id=member_user.id,
        weekly_allowance_units=100,
        ctx=CTX,
    )
    assert res["weekly_allowance_units"] == 100

    # Overview shows the member allocation (management-gated, org-scoped).
    overview = await admin_service.get_org_energy_overview(db_session, principal=admin)
    member_alloc = next(
        a for a in overview["allocations"]
        if a["scope_id"] == str(member_user.id)
    )
    assert member_alloc["weekly_allowance_units"] == 100
    assert member_alloc["enforced"] is True
    assert {p["code"] for p in overview["packs"]} == {"small", "medium", "large"}

    # The member's own snapshot carries the sub-allocation block.
    snap = await energy_service.snapshot(db_session, principal=member)
    pub = snap.to_public()
    assert pub["allocation"] is not None
    assert pub["allocation"]["allowance"] == 100
    assert pub["blocked"] is False  # nothing used yet

    # Consume the member's whole sub-cap (org pool default 400 is NOT exhausted).
    await _charge_member(db_session, org_id=org.id, user_id=member_user.id, units=100)
    snap2 = await energy_service.snapshot(db_session, principal=member)
    assert snap2.blocked is True
    assert snap2.blocked_reason == "AI_MEMBER_ALLOCATION_EXCEEDED"

    with pytest.raises(QuotaExceededError) as exc:
        await energy_service.enforce_energy(db_session, principal=member)
    assert exc.value.details["reason"] == "AI_MEMBER_ALLOCATION_EXCEEDED"


async def test_clear_subcap_shares_org_pool_again(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    member_user, _m, member = await add_member(db_session, org=org, permissions=[])
    await admin_service.set_allocation(
        db_session, principal=admin, scope_type=SCOPE_USER,
        scope_id=member_user.id, weekly_allowance_units=50, ctx=CTX,
    )
    # Clear it (None) → the member shares the org pool, no personal block.
    await admin_service.set_allocation(
        db_session, principal=admin, scope_type=SCOPE_USER,
        scope_id=member_user.id, weekly_allowance_units=None, ctx=CTX,
    )
    await _charge_member(db_session, org_id=org.id, user_id=member_user.id, units=100)
    snap = await energy_service.snapshot(db_session, principal=member)
    assert snap.to_public()["allocation"] is None
    assert snap.blocked is False  # org pool (400) still has headroom


# --------------------------------------------------------------------------- #
# (b) + (c) top-up request -> confirm -> credit -> idempotent                   #
# --------------------------------------------------------------------------- #


async def test_member_topup_request_then_confirm_credits_and_idempotent(
    db_session,
) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    member_user, _m, member = await add_member(db_session, org=org, permissions=[])
    await admin_service.set_allocation(
        db_session, principal=admin, scope_type=SCOPE_USER,
        scope_id=member_user.id, weekly_allowance_units=100, ctx=CTX,
    )

    before = await energy_service.snapshot(db_session, principal=member)
    assert before.to_public()["allocation"]["capacity"] == 100  # wallet 0

    # Member self-requests a pack (no admin capability needed).
    req = await admin_service.request_topup(
        db_session, principal=member, pack_code="small", ctx=CTX
    )
    assert req["status"] == TOPUP_PENDING
    assert req["scope_type"] == SCOPE_USER
    assert req["scope_id"] == str(member_user.id)
    assert req["payment_instructions"]["method"] == "bank_transfer"
    topup_id = uuid.UUID(req["id"])

    # Finance (university admin) confirms money received.
    _fu, _fo, finance = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    paid = await admin_service.confirm_topup(
        db_session, principal=finance, topup_id=topup_id,
        payment_reference="BANK-REF-77", ctx=CTX,
    )
    assert paid["status"] == TOPUP_PAID

    acct = await _account(db_session, SCOPE_USER, member_user.id)
    assert acct is not None and acct.wallet_units == SMALL_UNITS

    after = await energy_service.snapshot(db_session, principal=member)
    assert after.to_public()["allocation"]["capacity"] == 100 + SMALL_UNITS
    assert after.to_public()["allocation"]["wallet"] == SMALL_UNITS

    # (c) Re-confirming is a no-op — never double-credits.
    again = await admin_service.confirm_topup(
        db_session, principal=finance, topup_id=topup_id,
        payment_reference="BANK-REF-DUP", ctx=CTX,
    )
    assert again["status"] == TOPUP_PAID
    acct2 = await _account(db_session, SCOPE_USER, member_user.id)
    assert acct2 is not None and acct2.wallet_units == SMALL_UNITS  # unchanged


async def test_confirm_by_superadmin_allowed(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    member_user, _m, member = await add_member(db_session, org=org, permissions=[])
    req = await admin_service.request_topup(
        db_session, principal=member, pack_code="medium", ctx=CTX
    )
    superadmin = Principal(
        user_id=uuid.uuid4(), persona="university_staff", is_superadmin=True
    )
    paid = await admin_service.confirm_topup(
        db_session, principal=superadmin, topup_id=uuid.UUID(req["id"]),
        payment_reference="SA-REF", ctx=CTX,
    )
    assert paid["status"] == TOPUP_PAID


# --------------------------------------------------------------------------- #
# (d) RBAC — a non-admin member cannot manage / confirm                         #
# --------------------------------------------------------------------------- #


async def test_non_admin_member_cannot_manage_or_confirm(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    member_user, _m, member = await add_member(db_session, org=org, permissions=[])
    other_user, _om, _other = await add_member(db_session, org=org, permissions=[])

    with pytest.raises(PermissionDeniedError):
        await admin_service.get_org_energy_overview(db_session, principal=member)
    with pytest.raises(PermissionDeniedError):
        await admin_service.set_allocation(
            db_session, principal=member, scope_type=SCOPE_USER,
            scope_id=other_user.id, weekly_allowance_units=50, ctx=CTX,
        )
    with pytest.raises(PermissionDeniedError):
        await admin_service.grant_wallet(
            db_session, principal=member, scope_type=SCOPE_USER,
            scope_id=other_user.id, units=50, reason="x", ctx=CTX,
        )

    # A member cannot confirm their own top-up (finance authority required).
    req = await admin_service.request_topup(
        db_session, principal=member, pack_code="small", ctx=CTX
    )
    with pytest.raises(PermissionDeniedError):
        await admin_service.confirm_topup(
            db_session, principal=member, topup_id=uuid.UUID(req["id"]),
            payment_reference="SELF", ctx=CTX,
        )
    # Even a partner ADMIN (*:*) cannot self-confirm (anti free-energy).
    with pytest.raises(PermissionDeniedError):
        await admin_service.confirm_topup(
            db_session, principal=admin, topup_id=uuid.UUID(req["id"]),
            payment_reference="SELF", ctx=CTX,
        )


async def test_delegated_billing_manage_role_can_allocate(db_session) -> None:
    """Capability-gated, not role-name gated: a granted ``billing:manage`` role
    (not the org Admin) may allocate."""
    _u, org, _admin = await make_org_with_admin(db_session)
    target_user, _tm, _t = await add_member(db_session, org=org, permissions=[])
    _du, _dm, delegate = await add_member(
        db_session, org=org, permissions=[("billing", "manage")],
        role_name="Energy Manager",
    )
    res = await admin_service.set_allocation(
        db_session, principal=delegate, scope_type=SCOPE_USER,
        scope_id=target_user.id, weekly_allowance_units=70, ctx=CTX,
    )
    assert res["weekly_allowance_units"] == 70


# --------------------------------------------------------------------------- #
# (e) cross-org isolation                                                       #
# --------------------------------------------------------------------------- #


async def test_cross_org_allocation_denied(db_session) -> None:
    _ua, org_a, admin_a = await make_org_with_admin(db_session, display_name="Org A")
    _ub, org_b, _admin_b = await make_org_with_admin(db_session, display_name="Org B")
    b_member_user, _bm, _b = await add_member(db_session, org=org_b, permissions=[])

    # Org A admin cannot allocate to an Org B member.
    with pytest.raises(PermissionDeniedError):
        await admin_service.set_allocation(
            db_session, principal=admin_a, scope_type=SCOPE_USER,
            scope_id=b_member_user.id, weekly_allowance_units=50, ctx=CTX,
        )

    # ...nor to an Org B department.
    dept_b = Department(org_id=org_b.id, name="B-Dept")
    db_session.add(dept_b)
    await db_session.commit()
    with pytest.raises(PermissionDeniedError):
        await admin_service.set_allocation(
            db_session, principal=admin_a, scope_type=SCOPE_DEPARTMENT,
            scope_id=dept_b.id, weekly_allowance_units=50, ctx=CTX,
        )


async def test_admin_topups_are_org_scoped(db_session) -> None:
    _ua, org_a, admin_a = await make_org_with_admin(db_session, display_name="Org A")
    a_member_user, _am, a_member = await add_member(
        db_session, org=org_a, permissions=[]
    )
    _ub, org_b, admin_b = await make_org_with_admin(db_session, display_name="Org B")

    await admin_service.request_topup(
        db_session, principal=a_member, pack_code="small", ctx=CTX
    )
    a_list = await admin_service.list_org_topups(db_session, principal=admin_a)
    b_list = await admin_service.list_org_topups(db_session, principal=admin_b)
    assert len(a_list) == 1
    assert len(b_list) == 0  # Org B never sees Org A's top-ups


# --------------------------------------------------------------------------- #
# (f) self-service scope rules + org-scope grant needs finance                  #
# --------------------------------------------------------------------------- #


async def test_member_cannot_request_for_another_user(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(db_session)
    _mu, _m, member = await add_member(db_session, org=org, permissions=[])
    other_user, _om, _o = await add_member(db_session, org=org, permissions=[])
    with pytest.raises(PermissionDeniedError):
        await admin_service.request_topup(
            db_session, principal=member, pack_code="small",
            scope_type=SCOPE_USER, scope_id=other_user.id, ctx=CTX,
        )


async def test_invalid_pack_rejected(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(db_session)
    _mu, _m, member = await add_member(db_session, org=org, permissions=[])
    with pytest.raises(ValidationFailedError):
        await admin_service.request_topup(
            db_session, principal=member, pack_code="enormous", ctx=CTX
        )


async def test_org_scope_wallet_grant_requires_finance(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    # A partner admin (*:*) cannot mint org-wide wallet (finance authority only).
    with pytest.raises(PermissionDeniedError):
        await admin_service.grant_wallet(
            db_session, principal=admin, scope_type=SCOPE_ORG,
            scope_id=org.id, units=500, reason="goodwill", ctx=CTX,
        )
    # A member/department grant IS allowed under management (bounded by org pool).
    member_user, _m, _member = await add_member(db_session, org=org, permissions=[])
    res = await admin_service.grant_wallet(
        db_session, principal=admin, scope_type=SCOPE_USER,
        scope_id=member_user.id, units=40, reason="goodwill", ctx=CTX,
    )
    assert res["wallet_units"] == 40

    # Finance may mint org-wide wallet.
    _fu, _fo, finance = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    org_res = await admin_service.grant_wallet(
        db_session, principal=finance, scope_type=SCOPE_ORG,
        scope_id=org.id, units=500, reason="comp", ctx=CTX,
    )
    assert org_res["wallet_units"] == 500
    acct = await _account(db_session, SCOPE_ORG, org.id)
    assert acct is not None and acct.wallet_units == 500


async def test_confirmed_topup_is_audited(db_session) -> None:
    from app.shared.models import AuditLog

    _u, org, _admin = await make_org_with_admin(db_session)
    _mu, _m, member = await add_member(db_session, org=org, permissions=[])
    req = await admin_service.request_topup(
        db_session, principal=member, pack_code="small", ctx=CTX
    )
    _fu, _fo, finance = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    await admin_service.confirm_topup(
        db_session, principal=finance, topup_id=uuid.UUID(req["id"]),
        payment_reference="AUD-REF", ctx=CTX,
    )
    actions = set(
        (
            await db_session.execute(select(AuditLog.action))
        ).scalars().all()
    )
    assert "ai_energy.topup_requested" in actions
    assert "ai_energy.topup_paid" in actions

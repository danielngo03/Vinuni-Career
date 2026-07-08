"""University control plane — energy distribution resolution (WS1.1–WS1.3).

Covers: superadmin exemption; university user/department/org ceiling precedence;
block when the member OR the org pool is exhausted; no-regression when no account
rows exist (partner/student/university); persona-aware block copy + action; and
degrade-OPEN on an infra error.

All offline (SQLite) — no real LLM.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.energy import constants
from app.ai.energy import service as energy
from app.ai.energy.models import (
    SCOPE_DEPARTMENT,
    SCOPE_ORG,
    SCOPE_USER,
    AiEnergyAccount,
)
from app.ai.observability.models import AiBillableUsage
from app.modules.organization.domain.models import (
    Department,
    Membership,
    MembershipDepartment,
)
from app.shared.exceptions import QuotaExceededError
from app.shared.permissions import Principal


# --------------------------------------------------------------------------- #
# Fixtures / helpers                                                            #
# --------------------------------------------------------------------------- #


def _uni(org_id: uuid.UUID, user_id: uuid.UUID, *, superadmin: bool = False) -> Principal:
    return Principal(
        user_id=user_id,
        persona="university_staff",
        org_id=org_id,
        is_superadmin=superadmin,
    )


def _student(user_id: uuid.UUID) -> Principal:
    return Principal(user_id=user_id, persona="student")


def _partner(org_id: uuid.UUID, user_id: uuid.UUID) -> Principal:
    return Principal(user_id=user_id, persona="partner_member", org_id=org_id)


async def _usage(
    session,
    *,
    units: int,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    persona: str = "university",
    scope: str = "user",
) -> None:
    session.add(
        AiBillableUsage(
            actor_user_id=user_id,
            actor_persona=persona,
            org_id=org_id,
            department_id=department_id,
            billing_scope=scope,
            feature_key="chatbot",
            task_type="ai_assistant_chat",
            units_charged=units,
            result_status="success",
        )
    )
    await session.commit()


async def _account(
    session, *, scope_type: str, scope_id: uuid.UUID, ceiling: int | None,
    org_id: uuid.UUID | None = None, wallet: int = 0,
) -> None:
    session.add(
        AiEnergyAccount(
            scope_type=scope_type,
            scope_id=scope_id,
            org_id=org_id,
            weekly_allowance_units=ceiling,
            wallet_units=wallet,
        )
    )
    await session.commit()


async def _assign_department(
    session, *, org_id: uuid.UUID, user_id: uuid.UUID, name: str = "Dept"
) -> uuid.UUID:
    dept = Department(org_id=org_id, name=name)
    session.add(dept)
    await session.flush()
    # Reuse the member's single membership (unique per user+org).
    from sqlalchemy import select

    membership_id = (
        await session.execute(
            select(Membership.id).where(
                Membership.user_id == user_id, Membership.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if membership_id is None:
        membership = Membership(
            user_id=user_id, org_id=org_id, identity_id=uuid.uuid4(), status="active"
        )
        session.add(membership)
        await session.flush()
        membership_id = membership.id
    session.add(
        MembershipDepartment(membership_id=membership_id, department_id=dept.id)
    )
    await session.commit()
    return dept.id


# --------------------------------------------------------------------------- #
# WS1.1 — superadmin exemption                                                  #
# --------------------------------------------------------------------------- #


async def test_superadmin_snapshot_is_unlimited(db_session) -> None:
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    # Even with heavy usage + a tiny ceiling, superadmin is never limited.
    await _account(db_session, scope_type=SCOPE_USER, scope_id=user_id, ceiling=10)
    await _usage(db_session, units=9999, user_id=user_id, org_id=org_id)

    snap = await energy.snapshot(db_session, principal=_uni(org_id, user_id, superadmin=True))
    assert snap.unlimited is True
    assert snap.blocked is False
    assert snap.energy_pct == 100
    pub = snap.to_public()
    assert pub["action"] == constants.ACTION_UNLIMITED
    assert pub["unlimited"] is True


async def test_enforce_energy_superadmin_never_blocks(db_session) -> None:
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _account(db_session, scope_type=SCOPE_USER, scope_id=user_id, ceiling=5)
    await _usage(db_session, units=500, user_id=user_id, org_id=org_id)
    # Must not raise.
    await energy.enforce_energy(
        db_session, principal=_uni(org_id, user_id, superadmin=True)
    )


# --------------------------------------------------------------------------- #
# WS1.2 — university precedence + block conditions                              #
# --------------------------------------------------------------------------- #


async def test_university_no_rows_no_regression(db_session) -> None:
    """No account rows → meter on user scope at the persona default; not blocked."""
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _usage(db_session, units=100, user_id=user_id, org_id=org_id)

    snap = await energy.snapshot(db_session, principal=_uni(org_id, user_id))
    assert snap.scope == "user"
    assert snap.weekly_allowance == constants.DEFAULT_WEEKLY_UNITS_UNIVERSITY
    assert snap.blocked is False
    assert snap.action == constants.ACTION_REQUEST_CAPACITY


async def test_university_user_ceiling_blocks_member(db_session) -> None:
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _account(db_session, scope_type=SCOPE_USER, scope_id=user_id, ceiling=50)
    await _usage(db_session, units=60, user_id=user_id, org_id=org_id)

    snap = await energy.snapshot(db_session, principal=_uni(org_id, user_id))
    assert snap.weekly_allowance == 50
    assert snap.blocked is True
    assert snap.blocked_reason == constants.REASON_UNIVERSITY_ALLOCATION_EXCEEDED


async def test_university_department_ceiling_uses_department_consumption(db_session) -> None:
    """A department ceiling blocks on the DEPARTMENT's consumption, not just the member's."""
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    dept_id = await _assign_department(db_session, org_id=org_id, user_id=user_id)
    await _account(
        db_session, scope_type=SCOPE_DEPARTMENT, scope_id=dept_id, ceiling=100,
        org_id=org_id,
    )
    # The tested member's OWN usage is 0; another member burned the department pool.
    other_user = uuid.uuid4()
    await _usage(
        db_session, units=120, user_id=other_user, org_id=org_id, department_id=dept_id
    )

    snap = await energy.snapshot(db_session, principal=_uni(org_id, user_id))
    assert snap.weekly_allowance == 100
    assert snap.blocked is True
    assert snap.blocked_reason == constants.REASON_UNIVERSITY_ALLOCATION_EXCEEDED


async def test_university_min_department_ceiling_binds(db_session) -> None:
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    # Member in two departments; the tighter (100) ceiling binds over 500.
    d1 = await _assign_department(db_session, org_id=org_id, user_id=user_id, name="A")
    d2 = await _assign_department(db_session, org_id=org_id, user_id=user_id, name="B")
    await _account(db_session, scope_type=SCOPE_DEPARTMENT, scope_id=d1, ceiling=500, org_id=org_id)
    await _account(db_session, scope_type=SCOPE_DEPARTMENT, scope_id=d2, ceiling=100, org_id=org_id)
    await _usage(db_session, units=120, org_id=org_id, department_id=d2)

    snap = await energy.snapshot(db_session, principal=_uni(org_id, user_id))
    assert snap.weekly_allowance == 100
    assert snap.blocked is True


async def test_university_user_ceiling_overrides_department(db_session) -> None:
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    dept_id = await _assign_department(db_session, org_id=org_id, user_id=user_id)
    await _account(db_session, scope_type=SCOPE_DEPARTMENT, scope_id=dept_id, ceiling=10, org_id=org_id)
    await _account(db_session, scope_type=SCOPE_USER, scope_id=user_id, ceiling=1000)
    await _usage(db_session, units=50, user_id=user_id, org_id=org_id, department_id=dept_id)

    snap = await energy.snapshot(db_session, principal=_uni(org_id, user_id))
    # User ceiling (1000) wins over the department ceiling (10); not blocked at 50.
    assert snap.weekly_allowance == 1000
    assert snap.blocked is False


async def test_university_org_pool_blocks_when_org_exhausted(db_session) -> None:
    """An explicit org ceiling blocks all members when org-wide consumption exceeds it."""
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _account(db_session, scope_type=SCOPE_ORG, scope_id=org_id, ceiling=100, org_id=org_id)
    # Member's own usage is tiny; another member exhausted the org pool.
    await _usage(db_session, units=150, user_id=uuid.uuid4(), org_id=org_id)

    snap = await energy.snapshot(db_session, principal=_uni(org_id, user_id))
    assert snap.blocked is True
    assert snap.blocked_reason == constants.REASON_UNIVERSITY_ALLOCATION_EXCEEDED


async def test_university_no_org_row_means_no_org_wide_cap(db_session) -> None:
    """Without an org ceiling row there is NO org-wide cap (permissive pre-distribution)."""
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    # Another member burned far more than the persona default org-wide.
    await _usage(db_session, units=9999, user_id=uuid.uuid4(), org_id=org_id)
    # The tested member's own usage is small.
    await _usage(db_session, units=10, user_id=user_id, org_id=org_id)

    snap = await energy.snapshot(db_session, principal=_uni(org_id, user_id))
    assert snap.blocked is False


# --------------------------------------------------------------------------- #
# WS1.3 — messaging + action                                                    #
# --------------------------------------------------------------------------- #


async def test_university_block_asks_admin_not_upgrade(db_session) -> None:
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _account(db_session, scope_type=SCOPE_USER, scope_id=user_id, ceiling=10)
    await _usage(db_session, units=20, user_id=user_id, org_id=org_id)

    with pytest.raises(QuotaExceededError) as exc:
        await energy.enforce_energy(db_session, principal=_uni(org_id, user_id))
    err = exc.value
    assert err.details["reason"] == constants.REASON_UNIVERSITY_ALLOCATION_EXCEEDED
    assert err.details["action"] == constants.ACTION_REQUEST_CAPACITY
    assert "quản trị viên" in err.message
    assert "nâng gói" not in err.message
    assert "mua thêm" not in err.message


async def test_action_field_per_persona(db_session) -> None:
    org_id = uuid.uuid4()
    su = await energy.snapshot(db_session, principal=_uni(org_id, uuid.uuid4(), superadmin=True))
    uni = await energy.snapshot(db_session, principal=_uni(org_id, uuid.uuid4()))
    stu = await energy.snapshot(db_session, principal=_student(uuid.uuid4()))
    par = await energy.snapshot(db_session, principal=_partner(org_id, uuid.uuid4()))
    assert su.action == constants.ACTION_UNLIMITED
    assert uni.action == constants.ACTION_REQUEST_CAPACITY
    assert stu.action == constants.ACTION_UPGRADE
    assert par.action == constants.ACTION_UPGRADE


# --------------------------------------------------------------------------- #
# No-regression: partner + student                                              #
# --------------------------------------------------------------------------- #


async def test_partner_no_sub_allocation_only_org_check(db_session) -> None:
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _usage(
        db_session, units=500, user_id=user_id, org_id=org_id, persona="partner", scope="org"
    )
    snap = await energy.snapshot(db_session, principal=_partner(org_id, user_id))
    assert snap.scope == "org"
    assert snap.blocked is True
    assert snap.blocked_reason == constants.REASON_ORG_WEEKLY_EXCEEDED


async def test_partner_user_sub_allocation_blocks_member(db_session) -> None:
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _account(db_session, scope_type=SCOPE_USER, scope_id=user_id, ceiling=10)
    await _usage(db_session, units=20, user_id=user_id, org_id=org_id, persona="partner")
    snap = await energy.snapshot(db_session, principal=_partner(org_id, user_id))
    assert snap.blocked is True
    assert snap.blocked_reason == constants.REASON_MEMBER_ALLOCATION_EXCEEDED


async def test_student_blocks_on_own_usage(db_session) -> None:
    user_id = uuid.uuid4()
    await _usage(
        db_session,
        units=constants.DEFAULT_WEEKLY_UNITS_STUDENT_EXTERNAL + 10,
        user_id=user_id,
        persona="student",
    )
    snap = await energy.snapshot(db_session, principal=_student(user_id))
    assert snap.scope == "user"
    assert snap.blocked is True
    assert snap.blocked_reason == constants.REASON_WEEKLY_EXCEEDED


# --------------------------------------------------------------------------- #
# Degrade OPEN on infra error                                                   #
# --------------------------------------------------------------------------- #


async def test_snapshot_degrades_open_on_error(db_session, monkeypatch) -> None:
    org_id, user_id = uuid.uuid4(), uuid.uuid4()

    async def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(energy, "_resolve_member_budget", boom)
    snap = await energy.snapshot(db_session, principal=_uni(org_id, user_id))
    assert snap.blocked is False
    assert snap.weekly_allowance == constants.DEFAULT_WEEKLY_UNITS_UNIVERSITY


async def test_enforce_energy_degrades_open_on_error(db_session, monkeypatch) -> None:
    org_id, user_id = uuid.uuid4(), uuid.uuid4()

    async def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(energy, "snapshot", boom)
    # Must not raise despite the failure.
    await energy.enforce_energy(db_session, principal=_uni(org_id, user_id))

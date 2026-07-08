"""Superadmin AI energy distribution API (WS1.6) — service tests.

Covers the upsert (user/department/org scope; tenant validation; clear-to-inherit;
permission gate) and the live distribution read-model. Offline (SQLite).
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.energy import constants, distribution
from app.ai.energy.models import SCOPE_DEPARTMENT, SCOPE_ORG, SCOPE_USER
from app.ai.observability.models import AiBillableUsage
from app.modules.ai_governance.application import allocation_service
from app.modules.organization.domain.models import Department
from app.shared.audit import AuditContext
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

from tests.org_utils import make_org_with_admin


def _superadmin() -> Principal:
    return Principal(user_id=uuid.uuid4(), persona="university_staff", is_superadmin=True)


def _ctx(principal: Principal) -> AuditContext:
    return AuditContext(actor_id=principal.user_id)


async def _add_department(db_session, org_id: uuid.UUID, name: str = "CS") -> uuid.UUID:
    dept = Department(org_id=org_id, name=name)
    db_session.add(dept)
    await db_session.commit()
    return dept.id


async def _usage(db_session, *, units, user_id=None, org_id=None, department_id=None) -> None:
    db_session.add(
        AiBillableUsage(
            actor_user_id=user_id,
            actor_persona="university",
            org_id=org_id,
            department_id=department_id,
            billing_scope="user",
            feature_key="chatbot",
            task_type="ai_assistant_chat",
            units_charged=units,
            result_status="success",
        )
    )
    await db_session.commit()


# --------------------------------------------------------------------------- #
# Upsert                                                                         #
# --------------------------------------------------------------------------- #


async def test_upsert_user_allocation(db_session) -> None:
    user, org, _admin = await make_org_with_admin(db_session, org_type="university")
    su = _superadmin()
    result = await allocation_service.upsert_allocation(
        db_session, principal=su, ctx=_ctx(su),
        scope_type=SCOPE_USER, scope_id=user.id, org_id=org.id,
        weekly_allowance_units=300,
    )
    assert result["weekly_allowance_units"] == 300
    acct = await distribution.get_account(db_session, scope_type=SCOPE_USER, scope_id=user.id)
    assert acct is not None and acct.weekly_allowance_units == 300


async def test_upsert_department_allocation(db_session) -> None:
    _user, org, _admin = await make_org_with_admin(db_session, org_type="university")
    dept_id = await _add_department(db_session, org.id)
    su = _superadmin()
    result = await allocation_service.upsert_allocation(
        db_session, principal=su, ctx=_ctx(su),
        scope_type=SCOPE_DEPARTMENT, scope_id=dept_id, org_id=org.id,
        weekly_allowance_units=500,
    )
    assert result["weekly_allowance_units"] == 500


async def test_upsert_org_allocation(db_session) -> None:
    _user, org, _admin = await make_org_with_admin(db_session, org_type="university")
    su = _superadmin()
    result = await allocation_service.upsert_allocation(
        db_session, principal=su, ctx=_ctx(su),
        scope_type=SCOPE_ORG, scope_id=org.id, org_id=org.id,
        weekly_allowance_units=5000,
    )
    assert result["weekly_allowance_units"] == 5000
    assert result["org_id"] == str(org.id)


async def test_upsert_clear_ceiling_to_inherit(db_session) -> None:
    user, org, _admin = await make_org_with_admin(db_session, org_type="university")
    su = _superadmin()
    await allocation_service.upsert_allocation(
        db_session, principal=su, ctx=_ctx(su),
        scope_type=SCOPE_USER, scope_id=user.id, org_id=org.id,
        weekly_allowance_units=300,
    )
    result = await allocation_service.upsert_allocation(
        db_session, principal=su, ctx=_ctx(su),
        scope_type=SCOPE_USER, scope_id=user.id, org_id=org.id,
        weekly_allowance_units=None,
    )
    assert result["weekly_allowance_units"] is None


async def test_upsert_rejects_department_not_in_org(db_session) -> None:
    _user, org, _admin = await make_org_with_admin(db_session, org_type="university")
    su = _superadmin()
    with pytest.raises(ValidationFailedError):
        await allocation_service.upsert_allocation(
            db_session, principal=su, ctx=_ctx(su),
            scope_type=SCOPE_DEPARTMENT, scope_id=uuid.uuid4(), org_id=org.id,
            weekly_allowance_units=100,
        )


async def test_upsert_rejects_user_not_member(db_session) -> None:
    _user, org, _admin = await make_org_with_admin(db_session, org_type="university")
    su = _superadmin()
    with pytest.raises(ValidationFailedError):
        await allocation_service.upsert_allocation(
            db_session, principal=su, ctx=_ctx(su),
            scope_type=SCOPE_USER, scope_id=uuid.uuid4(), org_id=org.id,
            weekly_allowance_units=100,
        )


async def test_upsert_requires_superadmin(db_session) -> None:
    user, org, admin = await make_org_with_admin(db_session, org_type="university")
    with pytest.raises(PermissionDeniedError):
        await allocation_service.upsert_allocation(
            db_session, principal=admin, ctx=_ctx(admin),
            scope_type=SCOPE_USER, scope_id=user.id, org_id=org.id,
            weekly_allowance_units=100,
        )


async def test_upsert_rejects_negative_units(db_session) -> None:
    user, org, _admin = await make_org_with_admin(db_session, org_type="university")
    su = _superadmin()
    with pytest.raises(ValidationFailedError):
        await allocation_service.upsert_allocation(
            db_session, principal=su, ctx=_ctx(su),
            scope_type=SCOPE_USER, scope_id=user.id, org_id=org.id,
            weekly_allowance_units=-5,
        )


# --------------------------------------------------------------------------- #
# Read model                                                                    #
# --------------------------------------------------------------------------- #


async def test_list_allocations_requires_superadmin(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    with pytest.raises(PermissionDeniedError):
        await allocation_service.list_allocations(db_session, principal=admin, org_id=org.id)


async def test_list_allocations_org_not_found(db_session) -> None:
    su = _superadmin()
    with pytest.raises(ResourceNotFoundError):
        await allocation_service.list_allocations(db_session, principal=su, org_id=uuid.uuid4())


async def test_list_allocations_read_model(db_session) -> None:
    user, org, _admin = await make_org_with_admin(db_session, org_type="university")
    dept_id = await _add_department(db_session, org.id, name="Engineering")
    su = _superadmin()

    # Distribute: a user ceiling + a department ceiling.
    await allocation_service.upsert_allocation(
        db_session, principal=su, ctx=_ctx(su),
        scope_type=SCOPE_USER, scope_id=user.id, org_id=org.id,
        weekly_allowance_units=100,
    )
    await allocation_service.upsert_allocation(
        db_session, principal=su, ctx=_ctx(su),
        scope_type=SCOPE_DEPARTMENT, scope_id=dept_id, org_id=org.id,
        weekly_allowance_units=1000,
    )
    # Consumption: org-wide, member, and department.
    await _usage(db_session, units=40, user_id=user.id, org_id=org.id)
    await _usage(db_session, units=250, org_id=org.id, department_id=dept_id)

    model = await allocation_service.list_allocations(db_session, principal=su, org_id=org.id)
    assert model["org_type"] == "university"
    # Org node: no explicit ceiling → effective persona default; used = sum org rows.
    assert model["org"]["weekly_allowance_units"] is None
    assert model["org"]["effective_allowance_units"] == constants.DEFAULT_WEEKLY_UNITS_UNIVERSITY
    assert model["org"]["units_used"] == 290

    member = next(m for m in model["members"] if m["scope_id"] == str(user.id))
    assert member["weekly_allowance_units"] == 100
    assert member["units_used"] == 40
    assert member["energy_pct"] == 60  # (100-40)/100

    dept = next(d for d in model["departments"] if d["scope_id"] == str(dept_id))
    assert dept["weekly_allowance_units"] == 1000
    assert dept["units_used"] == 250
    assert dept["energy_pct"] == 75  # (1000-250)/1000

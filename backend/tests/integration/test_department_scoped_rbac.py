"""Department-scoped RBAC (P2/WS2.1): resolver, assignment API, enforcement.

Proves the department-scope feature is strictly ADDITIVE with ZERO regression:

- NULL-only role assignments resolve to today's exact org-wide grants and an
  empty department map (``test_null_only_assignments_*``).
- A department-scoped role assignment grants access ONLY inside that department,
  NOT org-wide and NOT in another department.
- Org-wide grants and superadmin bypass are unaffected.
- The assignment API validates the department scope and audits the change.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.career_services.application import cohort_service
from app.modules.organization.application import (
    grant_resolver,
    membership_service,
    rbac_service,
)
from app.modules.organization.domain.models import MembershipRole
from app.modules.users.domain.models import Identity
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.models import AuditLog
from app.shared.permissions import Principal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_utils import CTX
from tests.career_services_utils import add_counselor
from tests.org_utils import make_org_with_admin

_COHORT_PERMS = [
    ("career_services_cohorts", "create"),
    ("career_services_cohorts", "read"),
    ("career_services_cohorts", "update"),
    ("career_services_cohorts", "delete"),
]


async def _identity(session: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID):
    return (
        await session.execute(
            select(Identity).where(
                Identity.user_id == user_id, Identity.org_id == org_id
            )
        )
    ).scalar_one()


async def _scoped_principal(
    session: AsyncSession, *, user, org_id: uuid.UUID
) -> Principal:
    """Build a Principal via the department-aware resolver (both grant sets)."""

    identity = await _identity(session, user_id=user.id, org_id=org_id)
    org_wide, dept_grants = await grant_resolver.resolve_scoped_grants(
        session, user_id=user.id, identity=identity
    )
    return Principal(
        user_id=user.id,
        persona=identity.persona,
        org_id=org_id,
        is_superadmin=False,
        permissions=org_wide,
        department_grants=dept_grants,
    )


async def _role_id_for(session: AsyncSession, membership_id: uuid.UUID) -> uuid.UUID:
    return (
        await session.execute(
            select(MembershipRole.role_id).where(
                MembershipRole.membership_id == membership_id
            )
        )
    ).scalar_one()


async def _make_dept(session: AsyncSession, *, admin: Principal, name: str) -> uuid.UUID:
    dept = await rbac_service.create_department(
        session, principal=admin, name=name, parent_id=None, ctx=CTX
    )
    return uuid.UUID(dept["id"])


# --------------------------------------------------------------------------- #
# Resolver: NULL-only rows == today's behavior (byte-for-byte)                #
# --------------------------------------------------------------------------- #


async def test_null_only_assignments_resolve_identical_grants(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(
        db_session, org_type="university"
    )
    user, _m, _p = await add_counselor(db_session, org=org, permissions=_COHORT_PERMS)
    identity = await _identity(db_session, user_id=user.id, org_id=org.id)

    org_wide, dept_grants = await grant_resolver.resolve_scoped_grants(
        db_session, user_id=user.id, identity=identity
    )
    legacy = await grant_resolver.resolve_grants(
        db_session, user_id=user.id, identity=identity
    )

    # No scoped rows -> empty department map, and the org-wide set is exactly the
    # backwards-compatible resolve_grants() result.
    assert dept_grants == {}
    assert org_wide == legacy
    assert "career_services_cohorts:create" in org_wide
    assert "account:*" in org_wide  # common baseline preserved


# --------------------------------------------------------------------------- #
# Assignment API: scope a role to a department (+ audit + validation)         #
# --------------------------------------------------------------------------- #


async def test_scoped_assignment_moves_grant_from_org_wide_to_department(
    db_session,
) -> None:
    admin_user, org, admin = await make_org_with_admin(
        db_session, org_type="university"
    )
    dept_a = await _make_dept(db_session, admin=admin, name="Engineering")

    user, membership, _p = await add_counselor(
        db_session, org=org, permissions=_COHORT_PERMS
    )
    role_id = await _role_id_for(db_session, membership.id)

    # Scope the counselor's role to Engineering via the real assignment path.
    result = await membership_service.update_member(
        db_session,
        principal=admin,
        membership_id=membership.id,
        role_ids=None,
        role_assignments=[(role_id, dept_a)],
        department_ids=None,
        version=None,
        ctx=CTX,
    )
    assert result["role_assignments"] == [
        {"role_id": str(role_id), "department_id": str(dept_a)}
    ]

    # Row persisted with the department scope.
    persisted = (
        await db_session.execute(
            select(MembershipRole.department_id).where(
                MembershipRole.membership_id == membership.id
            )
        )
    ).scalar_one()
    assert persisted == dept_a

    # Grants now live under the department, not org-wide.
    org_wide, dept_grants = await grant_resolver.resolve_scoped_grants(
        db_session,
        user_id=user.id,
        identity=await _identity(db_session, user_id=user.id, org_id=org.id),
    )
    assert "career_services_cohorts:create" not in org_wide
    assert dept_grants[dept_a] == frozenset(
        f"{r}:{a}" for r, a in _COHORT_PERMS
    )

    # Audit row records the scoped assignment.
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "membership.updated",
                AuditLog.resource_id == membership.id,
            )
        )
    ).scalar_one()
    assert audit.after_snapshot is not None
    assert audit.after_snapshot["role_scopes"] == [
        {"role_id": str(role_id), "department_id": str(dept_a)}
    ]


async def test_scoped_assignment_rejects_foreign_department(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(
        db_session, org_type="university"
    )
    _u, membership, _p = await add_counselor(
        db_session, org=org, permissions=_COHORT_PERMS
    )
    role_id = await _role_id_for(db_session, membership.id)

    with pytest.raises(ResourceNotFoundError):
        await membership_service.update_member(
            db_session,
            principal=admin,
            membership_id=membership.id,
            role_ids=None,
            role_assignments=[(role_id, uuid.uuid4())],  # not a dept of this org
            department_ids=None,
            version=None,
            ctx=CTX,
        )


async def test_role_ids_and_role_assignments_are_mutually_exclusive(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(
        db_session, org_type="university"
    )
    _u, membership, _p = await add_counselor(
        db_session, org=org, permissions=_COHORT_PERMS
    )
    role_id = await _role_id_for(db_session, membership.id)

    with pytest.raises(ValidationFailedError):
        await membership_service.update_member(
            db_session,
            principal=admin,
            membership_id=membership.id,
            role_ids=[role_id],
            role_assignments=[(role_id, None)],
            department_ids=None,
            version=None,
            ctx=CTX,
        )


async def test_duplicate_role_in_assignments_rejected(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(
        db_session, org_type="university"
    )
    dept_a = await _make_dept(db_session, admin=admin, name="Engineering")
    dept_b = await _make_dept(db_session, admin=admin, name="Business")
    _u, membership, _p = await add_counselor(
        db_session, org=org, permissions=_COHORT_PERMS
    )
    role_id = await _role_id_for(db_session, membership.id)

    # Same role scoped to two departments violates the (membership, role) PK.
    with pytest.raises(ValidationFailedError):
        await membership_service.update_member(
            db_session,
            principal=admin,
            membership_id=membership.id,
            role_ids=None,
            role_assignments=[(role_id, dept_a), (role_id, dept_b)],
            department_ids=None,
            version=None,
            ctx=CTX,
        )


async def test_legacy_role_ids_assignment_unchanged(db_session) -> None:
    """The org-wide ``role_ids`` path still writes NULL-scoped assignments."""

    _admin_user, org, admin = await make_org_with_admin(
        db_session, org_type="university"
    )
    _u, membership, _p = await add_counselor(
        db_session, org=org, permissions=_COHORT_PERMS
    )
    role_id = await _role_id_for(db_session, membership.id)

    result = await membership_service.update_member(
        db_session,
        principal=admin,
        membership_id=membership.id,
        role_ids=[role_id],
        role_assignments=None,
        department_ids=None,
        version=None,
        ctx=CTX,
    )
    assert result["role_assignments"] == [
        {"role_id": str(role_id), "department_id": None}
    ]
    persisted = (
        await db_session.execute(
            select(MembershipRole.department_id).where(
                MembershipRole.membership_id == membership.id
            )
        )
    ).scalar_one()
    assert persisted is None


# --------------------------------------------------------------------------- #
# End-to-end enforcement: cohort capability gated by department               #
# --------------------------------------------------------------------------- #


async def test_department_scoped_counselor_cohort_enforcement(db_session) -> None:
    admin_user, org, admin = await make_org_with_admin(
        db_session, org_type="university"
    )
    dept_a = await _make_dept(db_session, admin=admin, name="Engineering")
    dept_b = await _make_dept(db_session, admin=admin, name="Business")

    user, membership, _p = await add_counselor(
        db_session, org=org, permissions=_COHORT_PERMS
    )
    role_id = await _role_id_for(db_session, membership.id)
    await membership_service.update_member(
        db_session,
        principal=admin,
        membership_id=membership.id,
        role_ids=None,
        role_assignments=[(role_id, dept_a)],
        department_ids=None,
        version=None,
        ctx=CTX,
    )
    scoped = await _scoped_principal(db_session, user=user, org_id=org.id)

    # Can create a cohort inside the scoped department.
    created = await cohort_service.create_cohort(
        db_session, principal=scoped, name="Eng 2026",
        description=None, department_id=dept_a, ctx=CTX,
    )
    assert created["department_id"] == str(dept_a)

    # Cannot create in another department, nor an org-wide (department-less) cohort.
    with pytest.raises(PermissionDeniedError):
        await cohort_service.create_cohort(
            db_session, principal=scoped, name="Biz 2026",
            description=None, department_id=dept_b, ctx=CTX,
        )
    with pytest.raises(PermissionDeniedError):
        await cohort_service.create_cohort(
            db_session, principal=scoped, name="Org-wide 2026",
            description=None, department_id=None, ctx=CTX,
        )

    # Admin (org-wide *:*) seeds a Business-department cohort.
    biz = await cohort_service.create_cohort(
        db_session, principal=admin, name="Biz Cohort",
        description=None, department_id=dept_b, ctx=CTX,
    )

    # The scoped counselor may update the Engineering cohort but NOT the Business one.
    await cohort_service.update_cohort(
        db_session, principal=scoped, cohort_id=uuid.UUID(created["id"]),
        name="Eng 2026 (edited)", description=None, status=None, ctx=CTX,
    )
    with pytest.raises(PermissionDeniedError):
        await cohort_service.update_cohort(
            db_session, principal=scoped, cohort_id=uuid.UUID(biz["id"]),
            name="Hijacked", description=None, status=None, ctx=CTX,
        )


async def test_org_wide_counselor_unaffected_by_department_scope(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(
        db_session, org_type="university"
    )
    dept_a = await _make_dept(db_session, admin=admin, name="Engineering")
    dept_b = await _make_dept(db_session, admin=admin, name="Business")

    user, _m, _p = await add_counselor(db_session, org=org, permissions=_COHORT_PERMS)
    # Org-wide grant (no scoping applied) — build a department-aware principal.
    org_wide = await _scoped_principal(db_session, user=user, org_id=org.id)

    # Org-wide counselor can create cohorts in any department AND org-wide.
    for name, dept in (("A", dept_a), ("B", dept_b), ("Org", None)):
        out = await cohort_service.create_cohort(
            db_session, principal=org_wide, name=f"Cohort {name}",
            description=None, department_id=dept, ctx=CTX,
        )
        assert out["department_id"] == (str(dept) if dept else None)

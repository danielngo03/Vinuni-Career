"""Service-layer RBAC checker: deny/allow + tenant isolation."""

from __future__ import annotations

import uuid

import pytest
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import GUEST, Principal, permission_checker


def _principal(
    perms: set[str],
    org_id: uuid.UUID | None = None,
    sa: bool = False,
    department_grants: dict[uuid.UUID, frozenset[str]] | None = None,
) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="partner_member",
        org_id=org_id,
        is_superadmin=sa,
        permissions=frozenset(perms),
        department_grants=department_grants or {},
    )


def test_guest_requires_auth() -> None:
    with pytest.raises(AuthRequiredError):
        permission_checker.require(GUEST, "jobs", "read")


def test_missing_permission_denied() -> None:
    p = _principal({"jobs:read"})
    with pytest.raises(PermissionDeniedError):
        permission_checker.require(p, "jobs", "create")


def test_exact_permission_allows() -> None:
    p = _principal({"jobs:create"})
    permission_checker.require(p, "jobs", "create")  # no raise
    assert permission_checker.can(p, "jobs", "create")


def test_wildcard_resource_and_action() -> None:
    assert permission_checker.can(_principal({"jobs:*"}), "jobs", "delete")
    assert permission_checker.can(_principal({"*:read"}), "events", "read")
    assert permission_checker.can(_principal({"*"}), "anything", "any")


def test_superadmin_bypasses() -> None:
    assert permission_checker.can(_principal(set(), sa=True), "x", "y")


def test_tenant_isolation_blocks_cross_org() -> None:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    p = _principal({"jobs:read"}, org_id=org_a)
    # Same org allowed, other org blocked.
    assert permission_checker.can(p, "jobs", "read", resource_org_id=org_a)
    assert not permission_checker.can(p, "jobs", "read", resource_org_id=org_b)
    with pytest.raises(PermissionDeniedError):
        permission_checker.require(p, "jobs", "read", resource_org_id=org_b)


def test_superadmin_crosses_tenants() -> None:
    p = _principal(set(), org_id=uuid.uuid4(), sa=True)
    assert permission_checker.can(p, "jobs", "read", resource_org_id=uuid.uuid4())


# --------------------------------------------------------------------------- #
# Department-scoped grants (P2/WS2.1) — additive, zero regression.             #
# --------------------------------------------------------------------------- #


def test_no_department_grants_is_identical_to_today() -> None:
    """A principal with no department_grants behaves exactly as before, whether
    or not ``resource_department_id`` is supplied."""

    org = uuid.uuid4()
    dept = uuid.uuid4()
    p = _principal({"cohorts:read"}, org_id=org)
    # Org-wide grant still allows, with or without a department id present.
    assert permission_checker.can(p, "cohorts", "read", resource_org_id=org)
    assert permission_checker.can(
        p, "cohorts", "read", resource_org_id=org, resource_department_id=dept
    )
    # A grant it does not hold is still denied, department id notwithstanding.
    assert not permission_checker.can(
        p, "cohorts", "create", resource_org_id=org, resource_department_id=dept
    )


def test_department_scoped_grant_allows_only_within_that_department() -> None:
    org = uuid.uuid4()
    dept_a = uuid.uuid4()
    dept_b = uuid.uuid4()
    # No org-wide grant; the grant exists ONLY inside dept_a.
    p = _principal(
        set(), org_id=org, department_grants={dept_a: frozenset({"cohorts:update"})}
    )
    # Allowed inside the scoped department.
    assert permission_checker.can(
        p, "cohorts", "update", resource_org_id=org, resource_department_id=dept_a
    )
    # Denied in a different department.
    assert not permission_checker.can(
        p, "cohorts", "update", resource_org_id=org, resource_department_id=dept_b
    )
    # Denied org-wide (no department id supplied == org-wide action).
    assert not permission_checker.can(p, "cohorts", "update", resource_org_id=org)
    # Denied for an action the scoped grant does not confer.
    assert not permission_checker.can(
        p, "cohorts", "delete", resource_org_id=org, resource_department_id=dept_a
    )


def test_org_wide_grant_short_circuits_before_department_lookup() -> None:
    """An org-wide grant allows any department; the department map is not needed."""

    org = uuid.uuid4()
    dept = uuid.uuid4()
    p = _principal({"cohorts:*"}, org_id=org)
    assert permission_checker.can(
        p, "cohorts", "delete", resource_org_id=org, resource_department_id=dept
    )


def test_department_grant_respects_tenant_isolation() -> None:
    """A department-scoped grant never crosses the org tenant boundary."""

    org = uuid.uuid4()
    other_org = uuid.uuid4()
    dept = uuid.uuid4()
    p = _principal(
        set(), org_id=org, department_grants={dept: frozenset({"cohorts:update"})}
    )
    # Same dept id but the resource is declared to belong to another org → deny.
    assert not permission_checker.can(
        p, "cohorts", "update",
        resource_org_id=other_org, resource_department_id=dept,
    )


def test_department_scoped_grant_supports_wildcards() -> None:
    org = uuid.uuid4()
    dept = uuid.uuid4()
    p = _principal(
        set(), org_id=org, department_grants={dept: frozenset({"cohorts:*"})}
    )
    assert permission_checker.can(
        p, "cohorts", "create", resource_org_id=org, resource_department_id=dept
    )
    assert permission_checker.can(
        p, "cohorts", "delete", resource_org_id=org, resource_department_id=dept
    )


def test_superadmin_bypasses_regardless_of_department() -> None:
    p = _principal(set(), org_id=uuid.uuid4(), sa=True)
    assert permission_checker.can(
        p, "cohorts", "update",
        resource_org_id=uuid.uuid4(), resource_department_id=uuid.uuid4(),
    )


def test_require_forwards_department_scope() -> None:
    org = uuid.uuid4()
    dept_a = uuid.uuid4()
    dept_b = uuid.uuid4()
    p = _principal(
        set(), org_id=org, department_grants={dept_a: frozenset({"cohorts:update"})}
    )
    # Allowed within scope — no raise.
    permission_checker.require(
        p, "cohorts", "update", resource_org_id=org, resource_department_id=dept_a
    )
    # Denied outside scope.
    with pytest.raises(PermissionDeniedError):
        permission_checker.require(
            p, "cohorts", "update", resource_org_id=org, resource_department_id=dept_b
        )

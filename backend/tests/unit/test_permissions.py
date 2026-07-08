"""Service-layer RBAC checker: deny/allow + tenant isolation."""

from __future__ import annotations

import uuid

import pytest
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import GUEST, Principal, permission_checker


def _principal(perms: set[str], org_id: uuid.UUID | None = None, sa: bool = False) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="partner_member",
        org_id=org_id,
        is_superadmin=sa,
        permissions=frozenset(perms),
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

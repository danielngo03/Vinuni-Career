"""Service-layer RBAC permission checker.

RBAC is enforced in the application/service layer, **not** only in routers
(``docs/SECURITY_PRIVACY.md``, ``docs/ARCHITECTURE.md`` §4.4). Every protected
use case calls :meth:`PermissionChecker.require`. Tenant isolation is enforced
here too: a principal cannot act on another organization's resource unless it is
a platform superadmin.

Permissions are strings of the form ``"{resource_type}:{action}"`` with ``*``
wildcards allowed (``"*"``, ``"jobs:*"``, ``"*:read"``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.shared.exceptions import AuthRequiredError, PermissionDeniedError


@dataclass(slots=True)
class Principal:
    """The acting identity for a request, resolved from the active session.

    ``permissions`` is the ORG-WIDE grant set (role assignments with no
    department scope). ``department_grants`` maps a ``department_id`` to the
    grant set that applies ONLY inside that department (role assignments scoped
    to that department via ``membership_roles.department_id``). It defaults to an
    empty dict, so every pre-existing ``Principal(...)`` construction site — and
    every principal without a department-scoped role — behaves exactly as before
    (``docs/PARTNER_RBAC_ANALYTICS_SPEC.md`` grantable-by-department model).
    """

    user_id: uuid.UUID | None
    persona: str = "guest"
    org_id: uuid.UUID | None = None
    is_superadmin: bool = False
    permissions: frozenset[str] = field(default_factory=frozenset)
    department_grants: dict[uuid.UUID, frozenset[str]] = field(default_factory=dict)

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None


GUEST = Principal(user_id=None, persona="guest")


def _matches(granted: str, resource_type: str, action: str) -> bool:
    if granted == "*":
        return True
    if ":" not in granted:
        return False
    g_resource, g_action = granted.split(":", 1)
    resource_ok = g_resource in ("*", resource_type)
    action_ok = g_action in ("*", action)
    return resource_ok and action_ok


class PermissionChecker:
    """Stateless RBAC decision point used by services."""

    def can(
        self,
        principal: Principal,
        resource_type: str,
        action: str,
        *,
        resource_org_id: uuid.UUID | None = None,
        resource_department_id: uuid.UUID | None = None,
    ) -> bool:
        if not principal.is_authenticated:
            return False
        if principal.is_superadmin:
            return True

        # Tenant isolation: org-scoped resources require matching org context.
        if resource_org_id is not None and principal.org_id != resource_org_id:
            return False

        # Org-wide grants (role assignments with department_id IS NULL). This
        # branch is byte-for-byte identical to the pre-department behavior: when
        # ``resource_department_id`` is absent AND the principal has no
        # department-scoped grants, only this check runs.
        if any(_matches(g, resource_type, action) for g in principal.permissions):
            return True

        # Department-scoped grants: consulted ONLY when the caller supplies the
        # resource's department and the principal holds a grant scoped to exactly
        # that department. Absent either, the result above stands (== today).
        if resource_department_id is not None:
            dept_grants = principal.department_grants.get(resource_department_id)
            if dept_grants is not None and any(
                _matches(g, resource_type, action) for g in dept_grants
            ):
                return True

        return False

    def require(
        self,
        principal: Principal,
        resource_type: str,
        action: str,
        *,
        resource_org_id: uuid.UUID | None = None,
        resource_department_id: uuid.UUID | None = None,
    ) -> None:
        """Raise if the principal may not perform ``action`` on ``resource_type``.

        - Unauthenticated -> :class:`AuthRequiredError` (401)
        - Authenticated but not permitted -> :class:`PermissionDeniedError` (403)
        """

        if not principal.is_authenticated:
            raise AuthRequiredError()
        if not self.can(
            principal,
            resource_type,
            action,
            resource_org_id=resource_org_id,
            resource_department_id=resource_department_id,
        ):
            raise PermissionDeniedError()


# Default shared instance.
permission_checker = PermissionChecker()

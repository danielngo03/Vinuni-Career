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
    """The acting identity for a request, resolved from the active session."""

    user_id: uuid.UUID | None
    persona: str = "guest"
    org_id: uuid.UUID | None = None
    is_superadmin: bool = False
    permissions: frozenset[str] = field(default_factory=frozenset)

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
    ) -> bool:
        if not principal.is_authenticated:
            return False
        if principal.is_superadmin:
            return True

        # Tenant isolation: org-scoped resources require matching org context.
        if resource_org_id is not None and principal.org_id != resource_org_id:
            return False

        return any(
            _matches(granted, resource_type, action) for granted in principal.permissions
        )

    def require(
        self,
        principal: Principal,
        resource_type: str,
        action: str,
        *,
        resource_org_id: uuid.UUID | None = None,
    ) -> None:
        """Raise if the principal may not perform ``action`` on ``resource_type``.

        - Unauthenticated -> :class:`AuthRequiredError` (401)
        - Authenticated but not permitted -> :class:`PermissionDeniedError` (403)
        """

        if not principal.is_authenticated:
            raise AuthRequiredError()
        if not self.can(
            principal, resource_type, action, resource_org_id=resource_org_id
        ):
            raise PermissionDeniedError()


# Default shared instance.
permission_checker = PermissionChecker()

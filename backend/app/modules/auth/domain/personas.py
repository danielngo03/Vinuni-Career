"""Phase 1a baseline persona -> permission grants.

This is a STATIC bootstrap map used until organization RBAC (Phase 1b) replaces
it with database-backed roles/permissions read from ``memberships`` +
``membership_roles`` + ``permissions``. Permission strings follow the
``"{resource}:{action}"`` form understood by ``PermissionChecker``.

Self-service account management (``account:*``) is available to every
authenticated persona. Org-scoped capabilities are intentionally NOT granted here
— they arrive with Phase 1b.
"""

from __future__ import annotations

STUDENT = "student"
PARTNER_MEMBER = "partner_member"
UNIVERSITY_STAFF = "university_staff"
ALUMNI = "alumni"
GUEST = "guest"

_COMMON = frozenset({"account:*", "notifications:read", "notifications:write"})

PERSONA_PERMISSIONS: dict[str, frozenset[str]] = {
    STUDENT: _COMMON
    | frozenset(
        {
            "cv:*", "profile:*", "applications:*", "jobs:read",
            "events:read", "events:register",
            # Student self-service subscription (ADR-0010): view plans + request a
            # paid tier for their own user-scoped subscription.
            "billing:view", "billing:subscribe",
        }
    ),
    ALUMNI: _COMMON
    | frozenset({"cv:*", "profile:*", "jobs:read", "events:read", "events:register"}),
    PARTNER_MEMBER: _COMMON | frozenset({"jobs:read", "applications:read"}),
    UNIVERSITY_STAFF: _COMMON,
    GUEST: frozenset(),
}


def permissions_for(persona: str) -> frozenset[str]:
    return PERSONA_PERMISSIONS.get(persona, frozenset())

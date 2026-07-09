"""Messaging RBAC capability checks (Messaging V2, owner decision 2026-07-09).

The org shared inbox is gated by a grantable ``messaging`` capability
(``organization/domain/catalog.py``), scoped by user/role/department — never a
hardcoded role name (`.claude/rules/backend.md` / `docs/PARTNER_RBAC_ANALYTICS_SPEC.md`).
Partner/University Admin hold the ``*:*`` wildcard and pass every check; superadmin
bypasses via the shared checker.

Recruitment application threads stay authorized by the application relationship
(``thread_service``/``message_service``), so this capability never regresses the
existing recruiter↔candidate flow — it governs only the NEW org-inbox / initiate /
internal / assign / moderate surfaces.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.messaging.domain.models import MessageThreadParty
from app.modules.organization.application import org_reporting_facade
from app.shared.permissions import Principal, permission_checker

RESOURCE = "messaging"


def _can(principal: Principal, action: str, org_id: uuid.UUID | None) -> bool:
    return permission_checker.can(principal, RESOURCE, action, resource_org_id=org_id)


def can_read_org_inbox(principal: Principal, org_id: uuid.UUID) -> bool:
    """May the caller see (some of) ``org_id``'s shared inbox at all."""

    return _can(principal, "read", org_id)


def can_send_as_org(principal: Principal, org_id: uuid.UUID) -> bool:
    """May the caller reply/send in ``org_id``'s threads."""

    return _can(principal, "send", org_id)


def can_initiate_as_org(principal: Principal, org_id: uuid.UUID) -> bool:
    """May the caller start a new outbound thread AS ``org_id`` (the Page)."""

    return _can(principal, "initiate", org_id)


def can_assign(principal: Principal, org_id: uuid.UUID) -> bool:
    """May the caller route/assign/resolve ``org_id``'s threads."""

    return _can(principal, "assign", org_id)


def can_moderate(principal: Principal, org_id: uuid.UUID | None = None) -> bool:
    """University compliance moderation (org-scoped grant, or superadmin)."""

    return _can(principal, "moderate", org_id)


async def member_can_access_org_party(
    session: AsyncSession, *, principal: Principal, party: MessageThreadParty
) -> bool:
    """Department-scope predicate for a staff member accessing an org-Page thread.

    This is the ACCESS-CONTROL gate for DIRECT thread reads, attachment
    download/upload, and first (lazy-participant) replies — not just the inbox
    listing — so a deep link or guessed id cannot cross a department boundary.
    It mirrors the shared-inbox scoping in ``inbox_service.list_org_inbox``:
    admins (``assign`` capability) and superadmins reach the whole org inbox; a
    plain member is scoped to unassigned threads, threads assigned to them, and
    threads assigned to one of their departments. Callers must SEPARATELY hold
    the relevant capability (``read`` for reads, ``send`` for replies) — this
    only answers "is this thread within the member's department scope".
    """

    org_id = party.org_id
    if org_id is None or principal.user_id is None:
        return False
    if principal.is_superadmin or can_assign(principal, org_id):
        return True
    if party.assigned_user_id == principal.user_id:
        return True
    if party.assigned_department_id is None:
        return True
    my_departments = await org_reporting_facade.department_ids_for_user_in_org(
        session, org_id=org_id, user_id=principal.user_id
    )
    return party.assigned_department_id in my_departments

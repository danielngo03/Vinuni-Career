"""Roles, role permissions, and departments (org-scoped RBAC management).

Every method enforces RBAC + tenant isolation at this layer and writes audit.
Security-critical invariants (escalation ceiling, last-admin protection,
system-role immutability) live in ``admin_guard`` + here (ADR-0002 §6.4).
Cross-tenant id lookups return 404 (enumeration hiding).
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.organization.api import presenters
from app.modules.organization.application import admin_guard
from app.modules.organization.application.errors import (
    DuplicateNameError,
    InvalidPermissionError,
    LastAdminError,
    SystemRoleImmutableError,
)
from app.modules.organization.application.org_resolution import resolve_managed_org
from app.modules.organization.domain import catalog
from app.modules.organization.domain.models import (
    Department,
    Permission,
    Role,
)
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker


def _audit_ctx(
    principal: Principal, ctx: RequestContext, *, org_id: uuid.UUID | None = None
) -> AuditContext:
    # ``org_id`` is the RESOLVED managed org (superadmin cross-org writes land in
    # that org's audit trail); for an ordinary actor it == ``principal.org_id``.
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=org_id if org_id is not None else principal.org_id,
        ip=ctx.ip, user_agent=ctx.user_agent,
    )


# --------------------------------------------------------------------------- #
# Roles                                                                       #
# --------------------------------------------------------------------------- #


async def _role_permission_strings(
    session: AsyncSession, role_id: uuid.UUID
) -> list[str]:
    rows = (
        await session.execute(
            select(Permission.resource_type, Permission.action).where(
                Permission.role_id == role_id
            )
        )
    ).all()
    return [f"{r}:{a}" for r, a in rows]


async def _get_role(
    session: AsyncSession, *, org_id: uuid.UUID, role_id: uuid.UUID
) -> Role | None:
    stmt = select(Role).where(Role.id == role_id, Role.org_id == org_id)
    return (await session.execute(stmt)).scalar_one_or_none()


def _validate_permissions(requested: list[tuple[str, str]]) -> None:
    for resource, action in requested:
        if not catalog.is_catalog_permission(resource, action):
            raise InvalidPermissionError()


async def list_roles(
    session: AsyncSession, *, principal: Principal,
    org_id: uuid.UUID | None = None, locale: str = "vi",
) -> list[dict]:
    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(principal, "roles", "read", resource_org_id=org_id)
    roles = (
        await session.execute(
            select(Role).where(Role.org_id == org_id).order_by(Role.created_at)
        )
    ).scalars().all()
    out = []
    for role in roles:
        perms = await _role_permission_strings(session, role.id)
        out.append(presenters.role_summary(role, permissions=perms))
    return out


async def get_role(
    session: AsyncSession, *, principal: Principal, role_id: uuid.UUID,
    org_id: uuid.UUID | None = None, locale: str = "vi",
) -> dict:
    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(principal, "roles", "read", resource_org_id=org_id)
    role = await _get_role(session, org_id=org_id, role_id=role_id)
    if role is None:
        raise ResourceNotFoundError()
    perms = await _role_permission_strings(session, role.id)
    return presenters.role_summary(role, permissions=perms)


async def create_role(
    session: AsyncSession,
    *,
    principal: Principal,
    name: str,
    description: str | None,
    permissions: list[tuple[str, str]],
    ctx: RequestContext,
    org_id: uuid.UUID | None = None,
) -> dict:
    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(principal, "roles", "create", resource_org_id=org_id)
    _validate_permissions(permissions)
    admin_guard.assert_can_grant(principal, permissions)

    existing = (
        await session.execute(
            select(Role.id).where(Role.org_id == org_id, Role.name == name)
        )
    ).first()
    if existing is not None:
        raise DuplicateNameError()

    role = Role(org_id=org_id, name=name, description=description, is_system=False)
    session.add(role)
    await session.flush()
    for resource, action in set(permissions):
        session.add(
            Permission(role_id=role.id, resource_type=resource, action=action)
        )
    await session.flush()
    await write_audit(
        session, action="role.created", resource_type="role", resource_id=role.id,
        context=_audit_ctx(principal, ctx, org_id=org_id),
        after={"name": name, "permissions": sorted(f"{r}:{a}" for r, a in permissions)},
    )
    await session.commit()
    perms = await _role_permission_strings(session, role.id)
    return presenters.role_summary(role, permissions=perms)


async def update_role(
    session: AsyncSession,
    *,
    principal: Principal,
    role_id: uuid.UUID,
    name: str | None,
    description: str | None,
    permissions: list[tuple[str, str]] | None,
    ctx: RequestContext,
    org_id: uuid.UUID | None = None,
) -> dict:
    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(principal, "roles", "update", resource_org_id=org_id)
    role = await _get_role(session, org_id=org_id, role_id=role_id)
    if role is None:
        raise ResourceNotFoundError()

    before_perms = await _role_permission_strings(session, role.id)

    if name is not None and name != role.name:
        if role.is_system:
            raise SystemRoleImmutableError()
        clash = (
            await session.execute(
                select(Role.id).where(
                    Role.org_id == org_id, Role.name == name, Role.id != role.id
                )
            )
        ).first()
        if clash is not None:
            raise DuplicateNameError()
        role.name = name
    if description is not None:
        role.description = description

    if permissions is not None:
        _validate_permissions(permissions)
        admin_guard.assert_can_grant(principal, permissions)
        new_set = set(permissions)
        had_admin = (catalog.ADMIN_WILDCARD_RESOURCE, catalog.ADMIN_WILDCARD_ACTION) in {
            tuple(p.split(":", 1)) for p in before_perms
        }
        will_have_admin = (
            catalog.ADMIN_WILDCARD_RESOURCE, catalog.ADMIN_WILDCARD_ACTION
        ) in new_set
        if role.is_system and not will_have_admin:
            # System Admin role must keep its *:* grant.
            raise SystemRoleImmutableError()
        if had_admin and not will_have_admin:
            # Removing *:* may strip the org's last admin.
            remaining = await admin_guard.admin_membership_ids(
                session, org_id=org_id, exclude_role_id=role.id
            )
            if not remaining:
                raise LastAdminError()
        # Replace permission rows.
        await session.execute(
            delete(Permission).where(Permission.role_id == role.id)
        )
        for resource, action in new_set:
            session.add(
                Permission(role_id=role.id, resource_type=resource, action=action)
            )

    await session.flush()
    await write_audit(
        session, action="role.updated", resource_type="role", resource_id=role.id,
        context=_audit_ctx(principal, ctx, org_id=org_id),
        before={"permissions": sorted(before_perms)},
        after={"permissions": sorted(await _role_permission_strings(session, role.id))},
    )
    await session.commit()
    perms = await _role_permission_strings(session, role.id)
    return presenters.role_summary(role, permissions=perms)


async def delete_role(
    session: AsyncSession, *, principal: Principal, role_id: uuid.UUID,
    ctx: RequestContext, org_id: uuid.UUID | None = None,
) -> None:
    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(principal, "roles", "delete", resource_org_id=org_id)
    role = await _get_role(session, org_id=org_id, role_id=role_id)
    if role is None:
        raise ResourceNotFoundError()
    if role.is_system:
        raise SystemRoleImmutableError()
    if await admin_guard.role_grants_admin(session, role_id=role.id):
        remaining = await admin_guard.admin_membership_ids(
            session, org_id=org_id, exclude_role_id=role.id
        )
        if not remaining:
            raise LastAdminError()
    await session.delete(role)
    await write_audit(
        session, action="role.deleted", resource_type="role", resource_id=role.id,
        context=_audit_ctx(principal, ctx, org_id=org_id), before={"name": role.name},
    )
    await session.commit()


# --------------------------------------------------------------------------- #
# Departments                                                                 #
# --------------------------------------------------------------------------- #


async def _get_department(
    session: AsyncSession, *, org_id: uuid.UUID, dept_id: uuid.UUID
) -> Department | None:
    stmt = select(Department).where(
        Department.id == dept_id, Department.org_id == org_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_departments(
    session: AsyncSession, *, principal: Principal,
    org_id: uuid.UUID | None = None,
) -> list[dict]:
    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(principal, "departments", "read", resource_org_id=org_id)
    depts = (
        await session.execute(
            select(Department).where(Department.org_id == org_id).order_by(
                Department.created_at
            )
        )
    ).scalars().all()
    return [presenters.department_summary(d) for d in depts]


async def create_department(
    session: AsyncSession,
    *,
    principal: Principal,
    name: str,
    parent_id: uuid.UUID | None,
    ctx: RequestContext,
    org_id: uuid.UUID | None = None,
) -> dict:
    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(
        principal, "departments", "create", resource_org_id=org_id
    )
    if parent_id is not None:
        parent = await _get_department(session, org_id=org_id, dept_id=parent_id)
        if parent is None:
            raise ValidationFailedError(details={"reason": "parent_not_found"})
    clash = (
        await session.execute(
            select(Department.id).where(
                Department.org_id == org_id, Department.name == name
            )
        )
    ).first()
    if clash is not None:
        raise DuplicateNameError()
    dept = Department(org_id=org_id, name=name, parent_id=parent_id)
    session.add(dept)
    await session.flush()
    await write_audit(
        session, action="department.created", resource_type="department",
        resource_id=dept.id, context=_audit_ctx(principal, ctx, org_id=org_id),
        after={"name": name},
    )
    await session.commit()
    return presenters.department_summary(dept)


async def update_department(
    session: AsyncSession,
    *,
    principal: Principal,
    dept_id: uuid.UUID,
    name: str | None,
    parent_id: uuid.UUID | None,
    clear_parent: bool,
    ctx: RequestContext,
    org_id: uuid.UUID | None = None,
) -> dict:
    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(
        principal, "departments", "update", resource_org_id=org_id
    )
    dept = await _get_department(session, org_id=org_id, dept_id=dept_id)
    if dept is None:
        raise ResourceNotFoundError()
    if name is not None and name != dept.name:
        clash = (
            await session.execute(
                select(Department.id).where(
                    Department.org_id == org_id, Department.name == name,
                    Department.id != dept.id,
                )
            )
        ).first()
        if clash is not None:
            raise DuplicateNameError()
        dept.name = name
    if clear_parent:
        dept.parent_id = None
    elif parent_id is not None:
        if parent_id == dept.id or await _would_cycle(
            session, org_id=org_id, dept_id=dept.id, new_parent=parent_id
        ):
            raise ValidationFailedError(details={"reason": "cyclic_parent"})
        parent = await _get_department(session, org_id=org_id, dept_id=parent_id)
        if parent is None:
            raise ValidationFailedError(details={"reason": "parent_not_found"})
        dept.parent_id = parent_id
    await session.flush()
    await write_audit(
        session, action="department.updated", resource_type="department",
        resource_id=dept.id, context=_audit_ctx(principal, ctx, org_id=org_id),
    )
    await session.commit()
    return presenters.department_summary(dept)


async def _would_cycle(
    session: AsyncSession, *, org_id: uuid.UUID, dept_id: uuid.UUID,
    new_parent: uuid.UUID,
) -> bool:
    """True if setting ``new_parent`` as parent of ``dept_id`` forms a cycle."""

    cursor: uuid.UUID | None = new_parent
    seen: set[uuid.UUID] = set()
    while cursor is not None:
        if cursor == dept_id:
            return True
        if cursor in seen:
            return True
        seen.add(cursor)
        row = (
            await session.execute(
                select(Department.parent_id).where(
                    Department.id == cursor, Department.org_id == org_id
                )
            )
        ).first()
        cursor = row[0] if row is not None else None
    return False


async def delete_department(
    session: AsyncSession, *, principal: Principal, dept_id: uuid.UUID,
    ctx: RequestContext, org_id: uuid.UUID | None = None,
) -> None:
    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(
        principal, "departments", "delete", resource_org_id=org_id
    )
    dept = await _get_department(session, org_id=org_id, dept_id=dept_id)
    if dept is None:
        raise ResourceNotFoundError()
    # membership_departments links cascade via FK; child departments are detached.
    await session.execute(
        update(Department)
        .where(Department.parent_id == dept.id)
        .values(parent_id=None)
    )
    await session.delete(dept)
    await write_audit(
        session, action="department.deleted", resource_type="department",
        resource_id=dept.id, context=_audit_ctx(principal, ctx, org_id=org_id),
        before={"name": dept.name},
    )
    await session.commit()

"""University control plane P2: superadmin org resolution, starter-role seed,
and service-layer taxonomy-grant enforcement (replacing the coarse persona gate).

Covers:
- superadmin resolves the single university org (default + explicit ``org_id``);
- non-superadmin behavior is byte-for-byte unchanged (404 on no org; the
  ``org_id`` param can NOT be used to cross tenants);
- starter-role seed idempotency + partner-org skip + valid catalog grants;
- ``taxonomy:manage`` enforced in the service layer: granted university member
  allowed, ungranted denied, wildcard-holding partner admin denied (org-type
  gate), superadmin allowed.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.modules.opportunities.application import industry_taxonomy_service
from app.modules.organization.application import organization_service, rbac_service
from app.modules.organization.application.org_resolution import resolve_managed_org
from app.modules.organization.application.role_seed import (
    STARTER_UNIVERSITY_ROLES,
    ensure_university_starter_roles,
)
from app.modules.organization.domain.catalog import is_catalog_permission
from app.modules.organization.domain.models import Organization, Role
from app.modules.users.domain.models import User
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.models import AuditLog
from app.shared.permissions import Principal

from tests.auth_utils import CTX, register_verified
from tests.org_utils import add_member, email, make_org_with_admin

_SEED_ROLE_NAMES = set(STARTER_UNIVERSITY_ROLES)


async def _make_superadmin(db_session) -> Principal:
    """A real, verified user promoted to platform superadmin (``org_id=None``)."""

    user = await register_verified(db_session, email=email("super"))
    row = (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalar_one()
    row.is_superadmin = True
    await db_session.commit()
    return Principal(
        user_id=user.id, persona="university_staff", org_id=None,
        is_superadmin=True, permissions=frozenset(),
    )


async def _audit_count(db_session, action: str) -> int:
    return (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Superadmin org resolution                                                   #
# --------------------------------------------------------------------------- #


async def test_superadmin_resolves_single_university_org_by_default(db_session) -> None:
    _u, uni, _admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    superadmin = await _make_superadmin(db_session)
    assert await resolve_managed_org(db_session, superadmin) == uni.id


async def test_superadmin_resolves_explicit_org_id(db_session) -> None:
    _u, uni, _a = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    _pu, partner, _pa = await make_org_with_admin(
        db_session, org_type="partner", display_name="Acme"
    )
    superadmin = await _make_superadmin(db_session)
    # Explicit id wins; default still resolves the university org.
    assert await resolve_managed_org(db_session, superadmin, org_id=partner.id) == partner.id
    assert await resolve_managed_org(db_session, superadmin) == uni.id


async def test_superadmin_missing_org_is_404(db_session) -> None:
    superadmin = await _make_superadmin(db_session)
    with pytest.raises(ResourceNotFoundError):
        await resolve_managed_org(db_session, superadmin)  # no university exists
    with pytest.raises(ResourceNotFoundError):
        await resolve_managed_org(db_session, superadmin, org_id=uuid.uuid4())


async def test_superadmin_lists_university_roles_default_and_explicit(db_session) -> None:
    _u, uni, _a = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    superadmin = await _make_superadmin(db_session)
    roles_default = await rbac_service.list_roles(db_session, principal=superadmin)
    assert any(r["name"] == "Admin" for r in roles_default)
    roles_explicit = await rbac_service.list_roles(
        db_session, principal=superadmin, org_id=uni.id
    )
    assert any(r["name"] == "Admin" for r in roles_explicit)


async def test_superadmin_get_current_org_loads_university(db_session) -> None:
    _u, uni, _a = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    superadmin = await _make_superadmin(db_session)
    data = await organization_service.get_organization(
        db_session, principal=superadmin
    )
    assert data["id"] == str(uni.id)
    assert data["org_type"] == "university"
    assert "max_team_members" in data  # seat info surfaced to the team screen


# --------------------------------------------------------------------------- #
# Non-superadmin: unchanged behavior + no cross-tenant via org_id              #
# --------------------------------------------------------------------------- #


async def test_non_superadmin_ignores_org_id_and_uses_own_org(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme")
    _u2, other, _a2 = await make_org_with_admin(db_session, display_name="Other")
    # Passing another org's id is silently ignored → own org resolved.
    assert await resolve_managed_org(db_session, admin, org_id=other.id) == org.id


async def test_non_superadmin_without_org_still_404(db_session) -> None:
    orphan = Principal(
        user_id=uuid.uuid4(), persona="student", org_id=None, is_superadmin=False
    )
    with pytest.raises(ResourceNotFoundError):
        await resolve_managed_org(db_session, orphan)


async def test_non_superadmin_cannot_cross_tenant_via_org_id_param(db_session) -> None:
    _ua, _org_a, admin_a = await make_org_with_admin(db_session, display_name="A")
    _ub, org_b, admin_b = await make_org_with_admin(db_session, display_name="B")
    await rbac_service.create_role(
        db_session, principal=admin_b, name="OnlyInB", description=None,
        permissions=[("jobs", "read")], ctx=CTX,
    )
    # admin_a targets org B via the param → still only sees org A's roles.
    roles = await rbac_service.list_roles(
        db_session, principal=admin_a, org_id=org_b.id
    )
    names = {r["name"] for r in roles}
    assert "OnlyInB" not in names
    assert "Admin" in names  # sanity: own org's system role is visible


# --------------------------------------------------------------------------- #
# Starter-role seed                                                           #
# --------------------------------------------------------------------------- #


def test_starter_role_grants_are_all_catalog_permissions() -> None:
    for name, (_desc, grants) in STARTER_UNIVERSITY_ROLES.items():
        for resource, action in grants:
            assert is_catalog_permission(resource, action), f"{name}: {resource}:{action}"


async def test_starter_role_seed_creates_then_idempotent(db_session) -> None:
    _u, uni, _a = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    created = await ensure_university_starter_roles(
        db_session, org_id=uni.id, actor_id=None, ctx=CTX
    )
    await db_session.commit()
    assert created == len(STARTER_UNIVERSITY_ROLES)

    created_again = await ensure_university_starter_roles(
        db_session, org_id=uni.id, actor_id=None, ctx=CTX
    )
    await db_session.commit()
    assert created_again == 0

    roles = (
        await db_session.execute(select(Role.name).where(Role.org_id == uni.id))
    ).scalars().all()
    names = set(roles)
    assert _SEED_ROLE_NAMES <= names
    assert "Admin" in names  # the pre-existing system role is untouched
    # No duplicate role names after two seed passes.
    assert len(roles) == len(names)


async def test_starter_roles_are_editable_not_system(db_session) -> None:
    _u, uni, _a = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    await ensure_university_starter_roles(
        db_session, org_id=uni.id, actor_id=None, ctx=CTX
    )
    await db_session.commit()
    seeded = (
        await db_session.execute(
            select(Role).where(Role.org_id == uni.id, Role.name.in_(_SEED_ROLE_NAMES))
        )
    ).scalars().all()
    assert seeded and all(r.is_system is False for r in seeded)


async def test_seed_skips_partner_org(db_session) -> None:
    _u, partner, _a = await make_org_with_admin(db_session, display_name="Acme")
    created = await ensure_university_starter_roles(
        db_session, org_id=partner.id, actor_id=None, ctx=CTX
    )
    await db_session.commit()
    assert created == 0
    names = set(
        (
            await db_session.execute(
                select(Role.name).where(Role.org_id == partner.id)
            )
        ).scalars().all()
    )
    assert "Moderation" not in names  # partner orgs are never seeded


async def test_create_university_org_seeds_starter_roles(db_session) -> None:
    superadmin = await _make_superadmin(db_session)
    await organization_service.create_university_org(
        db_session, principal=superadmin, display_name="VinUni", ctx=CTX
    )
    org = (
        await db_session.execute(
            select(Organization).where(Organization.org_type == "university")
        )
    ).scalar_one()
    names = set(
        (
            await db_session.execute(select(Role.name).where(Role.org_id == org.id))
        ).scalars().all()
    )
    assert _SEED_ROLE_NAMES <= names
    assert "Admin" in names


# --------------------------------------------------------------------------- #
# Taxonomy grant enforcement (service layer, not persona router gate)          #
# --------------------------------------------------------------------------- #


async def _make_industry(db_session, principal, *, slug: str):
    return await industry_taxonomy_service.create_industry(
        db_session, principal=principal, name_vi="Công nghệ", name_en="Technology",
        slug=slug, parent_id=None, sort_order=0, ctx=CTX,
    )


async def test_taxonomy_manage_granted_university_member_allowed(db_session) -> None:
    _u, uni, _admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    _mu, _m, granted = await add_member(
        db_session, org=uni, permissions=[("taxonomy", "manage")],
        role_name="TaxonomyMgr",
    )
    before = await _audit_count(db_session, "industry.created")
    row = await _make_industry(db_session, granted, slug="it-granted")
    assert row.slug == "it-granted"
    assert await _audit_count(db_session, "industry.created") == before + 1


async def test_taxonomy_manage_ungranted_university_member_denied(db_session) -> None:
    _u, uni, _admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    _mu, _m, ungranted = await add_member(
        db_session, org=uni, permissions=[("jobs", "read")], role_name="NoTaxonomy",
    )
    with pytest.raises(PermissionDeniedError):
        await _make_industry(db_session, ungranted, slug="it-denied")


async def test_taxonomy_partner_admin_wildcard_denied(db_session) -> None:
    # A partner Admin holds ``*:*`` (matches ``taxonomy:manage``) but is NOT a
    # university org → the org-type gate blocks it (behavior preserved).
    _u, _partner, partner_admin = await make_org_with_admin(
        db_session, org_type="partner", display_name="Acme"
    )
    with pytest.raises(PermissionDeniedError):
        await _make_industry(db_session, partner_admin, slug="it-partner")


async def test_taxonomy_university_admin_wildcard_allowed(db_session) -> None:
    # Current university-admin behavior is preserved: the ``*:*`` Admin passes.
    _u, _uni, uni_admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    row = await _make_industry(db_session, uni_admin, slug="it-uni-admin")
    assert row.slug == "it-uni-admin"


async def test_taxonomy_superadmin_allowed(db_session) -> None:
    superadmin = await _make_superadmin(db_session)
    row = await _make_industry(db_session, superadmin, slug="it-super")
    assert row.slug == "it-super"


async def test_taxonomy_update_and_deactivate_require_grant(db_session) -> None:
    _u, uni, _admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    _mu, _m, granted = await add_member(
        db_session, org=uni, permissions=[("taxonomy", "manage")], role_name="Tax",
    )
    _mu2, _m2, ungranted = await add_member(
        db_session, org=uni, permissions=[("jobs", "read")], role_name="NoTax",
    )
    row = await _make_industry(db_session, granted, slug="root")

    with pytest.raises(PermissionDeniedError):
        await industry_taxonomy_service.update_industry(
            db_session, principal=ungranted, industry_id=row.id, name_vi="X",
            name_en=None, sort_order=None, is_active=None, ctx=CTX,
        )
    with pytest.raises(PermissionDeniedError):
        await industry_taxonomy_service.deactivate_industry(
            db_session, principal=ungranted, industry_id=row.id, ctx=CTX,
        )

    updated = await industry_taxonomy_service.update_industry(
        db_session, principal=granted, industry_id=row.id, name_vi="Đã đổi",
        name_en=None, sort_order=None, is_active=None, ctx=CTX,
    )
    assert updated.name_vi == "Đã đổi"
    await industry_taxonomy_service.deactivate_industry(
        db_session, principal=granted, industry_id=row.id, ctx=CTX,
    )
    from app.modules.opportunities.domain.industry_models import Industry

    refreshed = await db_session.get(Industry, row.id)
    assert refreshed is not None and refreshed.is_active is False

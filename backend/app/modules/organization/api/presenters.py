"""ORM -> friendly response shapes. No raw enum codes leak to end users.

Each enum column is paired with a localized label via ``domain.catalog``; the raw
code is kept (clients may branch on it) but always accompanied by a human label.
"""

from __future__ import annotations

from app.modules.organization.api.public_presenters import public_logo_url
from app.modules.organization.domain import catalog
from app.modules.organization.domain.models import (
    Department,
    Invitation,
    Organization,
    PartnerRegistrationRequest,
    Role,
)


def organization_detail(org: Organization, *, locale: str = "vi") -> dict:
    return {
        "id": str(org.id),
        "slug": org.slug,
        "display_name": org.display_name,
        "org_type": org.org_type,
        # Safe delivery URL only; the raw ``logo_path`` storage key never leaves
        # the backend (docs/SECURITY_PRIVACY.md, .claude/rules/backend.md).
        "logo_url": public_logo_url(org),
        "website_url": org.website_url,
        "description": org.description,
        "industry": org.industry,
        "company_size": org.company_size,
        "founded_year": org.founded_year,
        "headquarters_city": org.headquarters_city,
        "is_verified": org.is_verified,
        "status": org.status,
        "status_label": catalog.status_label(org.status, locale=locale),
        "subscription_tier": org.subscription_tier,
        "max_team_members": org.max_team_members,  # -1 = unlimited
        "trust_level": org.trust_level,
        "owner_membership_id": (str(org.owner_membership_id) if org.owner_membership_id else None),
        "settings": org.settings,
        "version": org.version,
        "created_at": org.created_at.isoformat() if org.created_at else None,
    }


def role_summary(role: Role, *, permissions: list[str]) -> dict:
    return {
        "id": str(role.id),
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "permissions": sorted(permissions),
        "created_at": role.created_at.isoformat() if role.created_at else None,
    }


def department_summary(dept: Department) -> dict:
    return {
        "id": str(dept.id),
        "name": dept.name,
        "parent_id": str(dept.parent_id) if dept.parent_id else None,
        "created_at": dept.created_at.isoformat() if dept.created_at else None,
    }


def member_summary(
    *,
    membership,
    email: str,
    full_name: str | None,
    role_ids: list[str],
    department_ids: list[str],
    locale: str = "vi",
) -> dict:
    return {
        "id": str(membership.id),
        # Partner-internal: the member's user_id, needed for interview-assignee
        # selection. Org admins already see the member; this UUID is not PII.
        "user_id": str(membership.user_id),
        "user_email": email,
        "full_name": full_name,
        "status": membership.status,
        "status_label": catalog.member_status_label(membership.status, locale=locale),
        "role_ids": role_ids,
        "department_ids": department_ids,
        "version": membership.version,
        "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
    }


def invitation_summary(inv: Invitation, *, locale: str = "vi") -> dict:
    return {
        "id": str(inv.id),
        "email": inv.email,
        "role_id": str(inv.role_id) if inv.role_id else None,
        "department_id": str(inv.department_id) if inv.department_id else None,
        "status": inv.status,
        "status_label": catalog.invite_status_label(inv.status, locale=locale),
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }


def registration_summary(req: PartnerRegistrationRequest, *, locale: str = "vi") -> dict:
    return {
        "id": str(req.id),
        "company_name": req.company_name,
        "industry": req.industry,
        "company_size": req.company_size,
        "contact_name": req.contact_name,
        "contact_email": req.contact_email,
        "contact_title": req.contact_title,
        "status": req.status,
        "status_label": catalog.status_label(req.status, locale=locale),
        "review_note": req.review_note,
        "created_org_id": str(req.created_org_id) if req.created_org_id else None,
        "version": req.version,
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }

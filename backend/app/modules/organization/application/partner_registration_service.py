"""Partner self-registration -> university approval/rejection (ADR-0002 §5).

- Registration is public and anti-spam: it only writes a
  ``partner_registration_requests`` row (no org, no user yet).
- Approval is a single transaction that bootstraps the org + system Admin role +
  first admin user/identity/membership and enqueues an activation email.
- Rejection creates nothing. Both are idempotent / concurrency-safe.

Notifications go through the outbox only (no synchronous SMTP); a failed outbox
row never fails the product write.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application import auth_service
from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import feed_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.organization.api import presenters
from app.modules.organization.application import organization_service
from app.modules.organization.application.errors import (
    AlreadyRejectedError,
    DuplicateRegistrationError,
    VersionConflictError,
)
from app.modules.organization.domain import catalog
from app.modules.organization.domain.models import (
    Membership,
    Organization,
    PartnerRegistrationRequest,
)
from app.modules.users.application import user_service
from app.modules.workflow.application.trigger_service import dispatch_trigger
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "partners"


def _normalize_tax(tax_code: str | None) -> str | None:
    if tax_code is None:
        return None
    cleaned = tax_code.strip()
    return cleaned or None


def _activation_link(*, token: str, locale: str) -> str:
    base = get_settings().frontend_url.rstrip("/")
    return f"{base}/{locale}/auth/activate?token={token}"


async def _require_university_actor(
    session: AsyncSession, principal: Principal, action: str
) -> None:
    """Only a platform superadmin or a *university-org* member may review partners.

    A partner Admin holds ``*:*`` which would otherwise match ``partners:*``; the
    org-type gate ensures the partner-review surface is university-only
    (ADR-0002 §4.1, §5.2). The ``partners:{action}`` grant is still required for a
    university member (so a university staffer without it is denied).
    """

    if principal.is_superadmin:
        return
    permission_checker.require(principal, _RESOURCE, action)
    org_type = None
    if principal.org_id is not None:
        org_type = (
            await session.execute(
                select(Organization.org_type).where(Organization.id == principal.org_id)
            )
        ).scalar_one_or_none()
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "university_only"})


# --------------------------------------------------------------------------- #
# Registration (public)                                                       #
# --------------------------------------------------------------------------- #


async def _has_active_partner_membership(session: AsyncSession, email: str) -> bool:
    user = await user_service.get_by_email(session, email)
    if user is None:
        return False
    stmt = (
        select(Membership.id)
        .join(Organization, Organization.id == Membership.org_id)
        .where(
            Membership.user_id == user.id,
            Membership.status == "active",
            Organization.org_type == "partner",
            Organization.deleted_at.is_(None),
        )
    )
    return (await session.execute(stmt)).first() is not None


async def register_partner(
    session: AsyncSession,
    *,
    payload: dict,
    ctx: RequestContext,
    idempotency_key: str | None = None,
    locale: str = "vi",
) -> dict:
    norm_email = payload["contact_email"].strip().lower()
    norm_tax = _normalize_tax(payload.get("tax_code"))

    # Existing pending request for the same email -> idempotent or conflict.
    pending_email = (
        await session.execute(
            select(PartnerRegistrationRequest).where(
                func.lower(PartnerRegistrationRequest.contact_email) == norm_email,
                PartnerRegistrationRequest.status == "pending_review",
            )
        )
    ).scalar_one_or_none()
    if pending_email is not None:
        if idempotency_key is not None:
            return {
                "registration_id": str(pending_email.id),
                "status": "pending_review",
            }
        raise DuplicateRegistrationError()

    if norm_tax is not None:
        pending_tax = (
            await session.execute(
                select(PartnerRegistrationRequest.id).where(
                    PartnerRegistrationRequest.tax_code == norm_tax,
                    PartnerRegistrationRequest.status == "pending_review",
                )
            )
        ).first()
        if pending_tax is not None:
            raise DuplicateRegistrationError()

    if await _has_active_partner_membership(session, norm_email):
        raise DuplicateRegistrationError()

    req = PartnerRegistrationRequest(
        company_name=payload["company_name"],
        tax_code=norm_tax,
        company_website=payload.get("company_website"),
        company_size=payload.get("company_size"),
        industry=payload.get("industry"),
        description=payload.get("description"),
        contact_name=payload["contact_name"],
        contact_title=payload.get("contact_title"),
        contact_email=norm_email,
        contact_phone=payload.get("contact_phone"),
        logo_upload_id=payload.get("logo_upload_id"),
        status="pending_review",
    )
    session.add(req)
    try:
        await session.flush()
    except IntegrityError as exc:  # race: partial-unique backstop on Postgres
        await session.rollback()
        raise DuplicateRegistrationError() from exc

    await write_audit(
        session,
        action="partner_registration.submitted",
        resource_type="partner_registration_request",
        resource_id=req.id,
        context=AuditContext(ip=ctx.ip, user_agent=ctx.user_agent),
        after={"company_name": req.company_name},
    )
    await enqueue_notification(
        session,
        recipient_id=None,
        template_key="partner.registration_received",
        channel="email",
        locale=locale,
        variables={
            "email": norm_email,
            "name": req.contact_name,
            "company_name": req.company_name,
        },
        dedupe_key=f"partner_reg_recv:{req.id}",
    )
    await dispatch_trigger(
        session,
        trigger_type="system.partner_registered",
        payload={"registration_id": str(req.id), "company_name": req.company_name},
        idempotency_key=f"partner_registered:{req.id}",
    )
    await session.commit()
    return {"registration_id": str(req.id), "status": "pending_review"}


# --------------------------------------------------------------------------- #
# Review listing + approve/reject                                             #
# --------------------------------------------------------------------------- #


async def _load_request(
    session: AsyncSession, partner_id: uuid.UUID
) -> PartnerRegistrationRequest | None:
    stmt = select(PartnerRegistrationRequest).where(PartnerRegistrationRequest.id == partner_id)
    if get_settings().database_url.startswith("postgresql"):
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_request(
    session: AsyncSession,
    *,
    principal: Principal,
    partner_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    await _require_university_actor(session, principal, "read")
    req = (
        await session.execute(
            select(PartnerRegistrationRequest).where(PartnerRegistrationRequest.id == partner_id)
        )
    ).scalar_one_or_none()
    if req is None:
        raise ResourceNotFoundError()
    return presenters.registration_summary(req, locale=locale)


async def list_requests(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    locale: str = "vi",
) -> list[dict]:
    await _require_university_actor(session, principal, "read")
    stmt = select(PartnerRegistrationRequest)
    if status is not None:
        stmt = stmt.where(PartnerRegistrationRequest.status == status)
    stmt = stmt.order_by(PartnerRegistrationRequest.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [presenters.registration_summary(r, locale=locale) for r in rows]


async def approve_partner(
    session: AsyncSession,
    *,
    principal: Principal,
    partner_id: uuid.UUID,
    trust_level: str,
    package_id: uuid.UUID | None = None,
    note: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_university_actor(session, principal, "approve")
    if trust_level not in catalog.TRUST_LEVELS:
        raise ValidationFailedError(details={"reason": "invalid_trust_level"})

    req = await _load_request(session, partner_id)
    if req is None:
        raise ResourceNotFoundError()
    if version is not None and version != req.version:
        raise VersionConflictError()
    if req.status == "approved":
        # Idempotent: return the already-created org.
        return {"organization_id": str(req.created_org_id), "status": "approved"}
    if req.status == "rejected":
        raise AlreadyRejectedError("already_rejected")

    assert principal.user_id is not None
    user = await user_service.get_by_email(session, req.contact_email)
    new_user = user is None
    if user is None:
        user = await user_service.create_user(
            session,
            email=req.contact_email,
            password_hash=None,
            full_name=req.contact_name,
            preferred_language=locale,
        )

    # Phase 1b stores the chosen tier; full subscription record is later-phase.
    subscription_tier = "free"
    result = await organization_service.create_org_with_admin(
        session,
        org_type="partner",
        display_name=req.company_name,
        admin_user_id=user.id,
        admin_persona="partner_member",
        actor_id=principal.user_id,
        ctx=ctx,
        status="active",
        is_verified=True,
        verified_by=principal.user_id,
        trust_level=trust_level,
        subscription_tier=subscription_tier,
        company_fields={
            "industry": req.industry,
            "company_size": req.company_size,
            "website_url": req.company_website,
            "description": req.description,
        },
    )
    org = result.organization

    req.status = "approved"
    req.created_org_id = org.id
    req.reviewed_by = principal.user_id
    req.reviewed_at = datetime.now(tz=UTC)
    req.review_note = note
    req.version += 1
    await session.flush()

    await write_audit(
        session,
        action="partner_registration.approved",
        resource_type="partner_registration_request",
        resource_id=req.id,
        context=AuditContext(
            actor_id=principal.user_id, actor_org_id=org.id, ip=ctx.ip, user_agent=ctx.user_agent
        ),
        after={
            "organization_id": str(org.id),
            "trust_level": trust_level,
            "subscription_tier": subscription_tier,
            "package_id": str(package_id) if package_id else None,
        },
    )

    # Activation: passwordless admin sets a password + verifies via this token.
    activation_token = ""
    if new_user or user.password_hash is None:
        activation_token = await auth_service.issue_activation_token(session, user=user)
    await enqueue_notification(
        session,
        recipient_id=user.id,
        template_key="partner.registration_approved",
        channel="email",
        locale=locale,
        variables={
            "email": user.email,
            "name": req.contact_name,
            "company_name": req.company_name,
            "token": activation_token,
            "action_url": _activation_link(token=activation_token, locale=locale),
        },
        dedupe_key=f"partner_reg_approved:{req.id}",
    )
    # In-app feed row for the new partner admin (rejection has no platform user).
    await feed_service.create_in_app(
        session,
        recipient_id=user.id,
        notif_type="organization.partner_approved",
        action_url="/partner",
        variables={"company_name": req.company_name},
        locale=locale,
    )
    await session.commit()
    return {"organization_id": str(org.id), "status": "approved"}


async def reject_partner(
    session: AsyncSession,
    *,
    principal: Principal,
    partner_id: uuid.UUID,
    reason: str,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_university_actor(session, principal, "reject")
    if not reason or not reason.strip():
        raise ValidationFailedError(details={"reason": "reason_required"})

    req = await _load_request(session, partner_id)
    if req is None:
        raise ResourceNotFoundError()
    if version is not None and version != req.version:
        raise VersionConflictError()
    if req.status == "rejected":
        return {"registration_id": str(req.id), "status": "rejected"}
    if req.status == "approved":
        raise AlreadyRejectedError("already_approved")

    req.status = "rejected"
    req.review_note = reason
    req.reviewed_by = principal.user_id
    req.reviewed_at = datetime.now(tz=UTC)
    req.version += 1
    await session.flush()
    await write_audit(
        session,
        action="partner_registration.rejected",
        resource_type="partner_registration_request",
        resource_id=req.id,
        context=AuditContext(actor_id=principal.user_id, ip=ctx.ip, user_agent=ctx.user_agent),
        after={"status": "rejected"},
    )
    await enqueue_notification(
        session,
        recipient_id=None,
        template_key="partner.registration_rejected",
        channel="email",
        locale=locale,
        variables={
            "email": req.contact_email,
            "name": req.contact_name,
            "company_name": req.company_name,
            "reason": reason,
        },
        dedupe_key=f"partner_reg_rejected:{req.id}",
    )
    await session.commit()
    return {"registration_id": str(req.id), "status": "rejected"}

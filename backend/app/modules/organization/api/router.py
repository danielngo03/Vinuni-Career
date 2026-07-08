"""Organization, partner-registration, and admin-partner HTTP routes.

Routers are HTTP-only: validate, delegate to services (which enforce RBAC + audit
+ tenant isolation), and shape the response envelope. Org context for
``/organizations/*`` is implicit from ``principal.org_id``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.application.context import context_from_request
from app.modules.organization.api.schemas import (
    CampusOwnerSetRequest,
    CreateUniversityOrgRequest,
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
    InvitationCreateRequest,
    MemberUpdateRequest,
    NoteCreateRequest,
    OrganizationPatch,
    OwnershipTransferRequest,
    PartnerApproveRequest,
    PartnerRegistrationRequestBody,
    PartnerRejectRequest,
    PermissionPreviewRequest,
    RiskFlagCreateRequest,
    RiskFlagResolveRequest,
    RoleCreateRequest,
    RoleUpdateRequest,
)
from app.modules.organization.application import (
    audit_log_service,
    crm_service,
    logo_service,
    membership_service,
    organization_service,
    ownership_service,
    partner_registration_service,
    permission_preview_service,
    rbac_service,
)
from app.shared.exceptions import ValidationFailedError
from app.shared.responses import paginated, success

router = APIRouter(tags=["organization"])

org_router = APIRouter(prefix="/organizations")


def _perms(items) -> list[tuple[str, str]]:
    return [(p.resource, p.action) for p in items]


# --------------------------------------------------------------------------- #
# Organization profile                                                        #
# --------------------------------------------------------------------------- #


@org_router.get("", summary="Get current organization profile")
async def get_organization(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await organization_service.get_organization(session, principal=auth.principal)
    return success(data)


@org_router.post("", status_code=status.HTTP_201_CREATED,
                 summary="Bootstrap a university organization (superadmin only)")
async def create_university_org(
    body: CreateUniversityOrgRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await organization_service.create_university_org(
        session, principal=auth.principal, display_name=body.display_name, ctx=auth.ctx
    )
    return success(data)


@org_router.patch("", summary="Update current organization profile")
async def update_organization(
    body: OrganizationPatch,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await organization_service.update_organization(
        session, principal=auth.principal,
        payload=body.model_dump(exclude_unset=True), ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Company logo media (validated binary; gated by ``organizations:update``)    #
# --------------------------------------------------------------------------- #


@org_router.post("/{org_id}/logo", summary="Upload or replace the company logo")
async def upload_logo(
    org_id: uuid.UUID,
    file: UploadFile = File(...),
    version: int | None = Form(default=None),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await file.read()
    # Fail fast before any further buffering; the service validator re-checks.
    if len(data) > get_settings().org_logo_max_bytes:
        raise ValidationFailedError(
            "Tệp quá lớn. Hãy chọn ảnh logo nhỏ hơn.",
            details={"reason": "file_too_large"},
        )
    result = await logo_service.upload_logo(
        session, principal=auth.principal, org_id=org_id,
        filename=file.filename or "logo", data=data,
        content_type=file.content_type, expected_version=version, ctx=auth.ctx,
    )
    return success(result)


@org_router.delete("/{org_id}/logo", summary="Remove the company logo")
async def remove_logo(
    org_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    version: int | None = Query(default=None),
) -> dict:
    result = await logo_service.remove_logo(
        session, principal=auth.principal, org_id=org_id,
        expected_version=version, ctx=auth.ctx,
    )
    return success(result)


# --------------------------------------------------------------------------- #
# Roles                                                                       #
# --------------------------------------------------------------------------- #


@org_router.get("/roles", summary="List organization roles")
async def list_roles(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await rbac_service.list_roles(session, principal=auth.principal)
    return success(items, meta={"count": len(items)})


@org_router.post("/roles", status_code=status.HTTP_201_CREATED, summary="Create a role")
async def create_role(
    body: RoleCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await rbac_service.create_role(
        session, principal=auth.principal, name=body.name,
        description=body.description, permissions=_perms(body.permissions), ctx=auth.ctx,
    )
    return success(data)


@org_router.get("/roles/{role_id}", summary="Get a role")
async def get_role(
    role_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await rbac_service.get_role(session, principal=auth.principal, role_id=role_id)
    return success(data)


@org_router.patch("/roles/{role_id}", summary="Update a role")
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    perms = _perms(body.permissions) if body.permissions is not None else None
    data = await rbac_service.update_role(
        session, principal=auth.principal, role_id=role_id, name=body.name,
        description=body.description, permissions=perms, ctx=auth.ctx,
    )
    return success(data)


@org_router.delete("/roles/{role_id}", summary="Delete a role")
async def delete_role(
    role_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await rbac_service.delete_role(
        session, principal=auth.principal, role_id=role_id, ctx=auth.ctx
    )
    return success({"status": "deleted"})


# --------------------------------------------------------------------------- #
# Departments                                                                 #
# --------------------------------------------------------------------------- #


@org_router.get("/departments", summary="List departments")
async def list_departments(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await rbac_service.list_departments(session, principal=auth.principal)
    return success(items, meta={"count": len(items)})


@org_router.post("/departments", status_code=status.HTTP_201_CREATED,
                 summary="Create a department")
async def create_department(
    body: DepartmentCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await rbac_service.create_department(
        session, principal=auth.principal, name=body.name,
        parent_id=body.parent_id, ctx=auth.ctx,
    )
    return success(data)


@org_router.patch("/departments/{dept_id}", summary="Update a department")
async def update_department(
    dept_id: uuid.UUID,
    body: DepartmentUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await rbac_service.update_department(
        session, principal=auth.principal, dept_id=dept_id, name=body.name,
        parent_id=body.parent_id, clear_parent=body.clear_parent, ctx=auth.ctx,
    )
    return success(data)


@org_router.delete("/departments/{dept_id}", summary="Delete a department")
async def delete_department(
    dept_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await rbac_service.delete_department(
        session, principal=auth.principal, dept_id=dept_id, ctx=auth.ctx
    )
    return success({"status": "deleted"})


# --------------------------------------------------------------------------- #
# Members                                                                     #
# --------------------------------------------------------------------------- #


@org_router.get("/members", summary="List organization members")
async def list_members(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    member_status: str | None = Query(default=None, alias="status"),
    role_id: uuid.UUID | None = Query(default=None),
) -> dict:
    items, next_cursor, page_limit = await membership_service.list_members(
        session, principal=auth.principal, cursor=cursor, limit=limit,
        status=member_status, role_id=role_id,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@org_router.patch("/members/{membership_id}", summary="Update a member's roles/departments")
async def update_member(
    membership_id: uuid.UUID,
    body: MemberUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await membership_service.update_member(
        session, principal=auth.principal, membership_id=membership_id,
        role_ids=body.role_ids, department_ids=body.department_ids,
        version=body.version, ctx=auth.ctx,
    )
    return success(data)


@org_router.delete("/members/{membership_id}", summary="Remove a member (soft)")
async def remove_member(
    membership_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await membership_service.remove_member(
        session, principal=auth.principal, membership_id=membership_id, ctx=auth.ctx
    )
    return success({"status": "removed"})


@org_router.post(
    "/members/{membership_id}/deactivate",
    summary="Suspend a member's access (reversible)",
)
async def deactivate_member(
    membership_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await membership_service.deactivate_member(
        session, principal=auth.principal, membership_id=membership_id, ctx=auth.ctx
    )
    return success(data)


@org_router.post(
    "/members/{membership_id}/reactivate",
    summary="Restore a suspended member's access",
)
async def reactivate_member(
    membership_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await membership_service.reactivate_member(
        session, principal=auth.principal, membership_id=membership_id, ctx=auth.ctx
    )
    return success(data)


@org_router.get(
    "/members/{membership_id}/permission-preview",
    summary="Preview a member's effective capabilities",
)
async def member_permission_preview(
    membership_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await permission_preview_service.preview_for_member(
        session, principal=auth.principal, membership_id=membership_id
    )
    return success(data)


@org_router.post(
    "/permission-preview",
    summary="Preview effective capabilities for a hypothetical role/department set",
)
async def hypothetical_permission_preview(
    body: PermissionPreviewRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await permission_preview_service.preview_hypothetical(
        session, principal=auth.principal,
        role_ids=body.role_ids, department_ids=body.department_ids,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Ownership transfer                                                          #
# --------------------------------------------------------------------------- #


@org_router.get("/ownership", summary="Get the org's current designated owner")
async def get_ownership(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await ownership_service.get_ownership(session, principal=auth.principal)
    return success(data)


@org_router.post("/ownership/transfer", summary="Transfer org ownership")
async def transfer_ownership(
    body: OwnershipTransferRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await ownership_service.transfer_ownership(
        session, principal=auth.principal,
        target_membership_id=body.target_membership_id, confirm=body.confirm,
        ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Audit log                                                                   #
# --------------------------------------------------------------------------- #


@org_router.get("/audit-log", summary="Page through the org's audit trail")
async def list_audit_log(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> dict:
    items, next_cursor, page_limit = await audit_log_service.list_audit_log(
        session, principal=auth.principal, cursor=cursor, limit=limit,
        actor_id=actor_id, action=action, since=since, until=until,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


# --------------------------------------------------------------------------- #
# Employer CRM (B-553): profile quality, seats, campus owner, risk flags,     #
# university-only notes, event/campaign + hiring-outcome rollups.            #
# --------------------------------------------------------------------------- #


@org_router.get("/{org_id}/profile-quality", summary="Company profile completeness score")
async def get_profile_quality(
    org_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await crm_service.get_profile_quality(
        session, principal=auth.principal, org_id=org_id
    )
    return success(data)


@org_router.get("/{org_id}/recruiter-seats", summary="Active member count vs seat limit")
async def get_recruiter_seats(
    org_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await crm_service.recruiter_seats_summary(
        session, principal=auth.principal, org_id=org_id
    )
    return success(data)


@org_router.get("/{org_id}/crm/activity", summary="Event + campaign history rollup")
async def get_crm_activity(
    org_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await crm_service.event_campaign_rollup(
        session, principal=auth.principal, org_id=org_id
    )
    return success(data)


@org_router.get("/{org_id}/crm/hiring-outcomes", summary="Applications/hires/offers aggregate")
async def get_crm_hiring_outcomes(
    org_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await crm_service.hiring_outcomes(
        session, principal=auth.principal, org_id=org_id
    )
    return success(data)


@org_router.get(
    "/{org_id}/campus-owner", summary="Get the campus relationship owner (university-only)"
)
async def get_campus_owner(
    org_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await crm_service.get_campus_owner(
        session, principal=auth.principal, org_id=org_id
    )
    return success(data)


@org_router.put(
    "/{org_id}/campus-owner", summary="Set the campus relationship owner (university-only)"
)
async def set_campus_owner(
    org_id: uuid.UUID,
    body: CampusOwnerSetRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await crm_service.set_campus_owner(
        session, principal=auth.principal, org_id=org_id,
        owner_user_id=body.owner_user_id, ctx=auth.ctx,
    )
    return success(data)


@org_router.get(
    "/{org_id}/risk-flags", summary="List risk/trust flags (university-only)"
)
async def list_risk_flags(
    org_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await crm_service.list_risk_flags(
        session, principal=auth.principal, org_id=org_id
    )
    return success(items, meta={"count": len(items)})


@org_router.post(
    "/{org_id}/risk-flags", status_code=status.HTTP_201_CREATED,
    summary="Raise a risk/trust flag (university-only)",
)
async def raise_risk_flag(
    org_id: uuid.UUID,
    body: RiskFlagCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await crm_service.raise_risk_flag(
        session, principal=auth.principal, org_id=org_id,
        flag_type=body.flag_type, severity=body.severity, note=body.note,
        ctx=auth.ctx,
    )
    return success(data)


@org_router.post(
    "/{org_id}/risk-flags/{flag_id}/resolve",
    summary="Resolve a risk/trust flag (university-only)",
)
async def resolve_risk_flag(
    org_id: uuid.UUID,
    flag_id: uuid.UUID,
    body: RiskFlagResolveRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await crm_service.resolve_risk_flag(
        session, principal=auth.principal, org_id=org_id, flag_id=flag_id,
        resolution_note=body.resolution_note, ctx=auth.ctx,
    )
    return success(data)


@org_router.get("/{org_id}/notes", summary="List university-only CRM notes")
async def list_notes(
    org_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await crm_service.list_notes(
        session, principal=auth.principal, org_id=org_id
    )
    return success(items, meta={"count": len(items)})


@org_router.post(
    "/{org_id}/notes", status_code=status.HTTP_201_CREATED,
    summary="Add a university-only CRM note",
)
async def create_note(
    org_id: uuid.UUID,
    body: NoteCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await crm_service.create_note(
        session, principal=auth.principal, org_id=org_id, body=body.body, ctx=auth.ctx
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Invitations                                                                 #
# --------------------------------------------------------------------------- #


@org_router.get("/invitations", summary="List pending/expired invitations")
async def list_invitations(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await membership_service.list_invitations(session, principal=auth.principal)
    return success(items, meta={"count": len(items)})


@org_router.post("/invitations", status_code=status.HTTP_201_CREATED,
                 summary="Invite a member")
async def create_invitation(
    body: InvitationCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await membership_service.create_invitation(
        session, principal=auth.principal, email=body.email, role_id=body.role_id,
        department_id=body.department_id, ctx=auth.ctx,
    )
    return success(data)


@org_router.delete("/invitations/{invitation_id}", summary="Revoke an invitation")
async def revoke_invitation(
    invitation_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await membership_service.revoke_invitation(
        session, principal=auth.principal, invitation_id=invitation_id, ctx=auth.ctx
    )
    return success({"status": "revoked"})


@org_router.post("/invitations/{token}/accept", summary="Accept an invitation")
async def accept_invitation(
    token: str,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await membership_service.accept_invitation(
        session, principal=auth.principal, token=token, ctx=auth.ctx
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Partner registration (public) + admin review                               #
# --------------------------------------------------------------------------- #

partner_router = APIRouter()


@partner_router.post("/partner-registration", status_code=status.HTTP_201_CREATED,
                     summary="Submit a partner registration (public)")
async def partner_registration(
    body: PartnerRegistrationRequestBody,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    data = await partner_registration_service.register_partner(
        session,
        payload=body.model_dump(by_alias=False),
        ctx=context_from_request(request),
        idempotency_key=idempotency_key,
    )
    return success(data)


admin_partner_router = APIRouter(prefix="/admin/partners")


@admin_partner_router.get("", summary="List partner registration requests")
async def list_partner_requests(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    req_status: str | None = Query(default=None, alias="status"),
) -> dict:
    items = await partner_registration_service.list_requests(
        session, principal=auth.principal, status=req_status
    )
    return success(items, meta={"count": len(items)})


@admin_partner_router.get("/{partner_id}", summary="Get partner registration detail")
async def get_partner_request(
    partner_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await partner_registration_service.get_request(
        session, principal=auth.principal, partner_id=partner_id,
    )
    return success(data)


@admin_partner_router.post("/{partner_id}/approve", summary="Approve a partner")
async def approve_partner(
    partner_id: uuid.UUID,
    body: PartnerApproveRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await partner_registration_service.approve_partner(
        session, principal=auth.principal, partner_id=partner_id,
        trust_level=body.trust_level, package_id=body.package_id, note=body.note,
        version=body.version, ctx=auth.ctx,
    )
    return success(data)


@admin_partner_router.post("/{partner_id}/reject", summary="Reject a partner")
async def reject_partner(
    partner_id: uuid.UUID,
    body: PartnerRejectRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await partner_registration_service.reject_partner(
        session, principal=auth.principal, partner_id=partner_id,
        reason=body.reason, version=body.version, ctx=auth.ctx,
    )
    return success(data)


router.include_router(org_router)
router.include_router(partner_router)
router.include_router(admin_partner_router)

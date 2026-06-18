from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.access.api.identity import get_active_identity
from app.modules.access.api.rbac import require_permission
from app.modules.institution.api.schemas import (
    DepartmentCreate,
    DepartmentView,
    IndustryCreate,
    IndustryView,
    OrganizationCreate,
    OrganizationView,
    PartnerVerificationRequest,
    RegistrationReferenceData,
)
from app.modules.institution.application.service import (
    create_department,
    create_industry,
    create_organization,
    list_organizations,
    registration_reference_data,
)
from app.platform.database.models import Department, Industry, Organization, User, UserOrgRole
from app.platform.database.session import get_db
from app.shared.enum import OrgType
from app.shared.errors import AppError, ErrorCode
from app.shared.schemas import PageParams

router = APIRouter()


@router.get("/registration-reference", response_model=RegistrationReferenceData)
def get_registration_reference(
    university_org_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RegistrationReferenceData:
    return registration_reference_data(db, university_org_id)


@router.post("/industries", response_model=IndustryView, status_code=201)
def post_industry(
    payload: IndustryCreate,
    identity: UserOrgRole = Depends(get_active_identity),
    _: User = Depends(require_permission("taxonomy", "manage")),
    db: Session = Depends(get_db),
) -> Industry:
    if identity.org.type != OrgType.UNIVERSITY:
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="University identity required",
            status_code=403,
        )
    return create_industry(db, university_org_id=identity.org_id, payload=payload)


@router.post("", response_model=OrganizationView, status_code=201)
def create_org(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("org", "create")),
) -> Organization:
    return create_organization(db, payload)


@router.get("", response_model=list[OrganizationView])
def get_orgs(
    page: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Organization]:
    return list_organizations(db, limit=page.limit, offset=page.offset)


@router.put("/{org_id}/verification", response_model=OrganizationView)
def verify_partner(
    org_id: str,
    payload: PartnerVerificationRequest,
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
) -> Organization:
    if identity.org.type != OrgType.UNIVERSITY:
        raise AppError(
            code=ErrorCode.FORBIDDEN, message="University identity required", status_code=403
        )
    organization = db.get(Organization, org_id)
    if not organization or organization.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Organization not found", status_code=404)
    if organization.type != OrgType.PARTNER:
        raise AppError(
            code=ErrorCode.BAD_REQUEST, message="Organization is not a partner", status_code=400
        )
    organization.is_verified_partner = payload.is_verified
    db.commit()
    db.refresh(organization)
    return organization


@router.post("/departments", response_model=DepartmentView, status_code=201)
def create_org_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Department:
    return create_department(db, payload)

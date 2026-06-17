from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.rbac import require_permission
from app.infra.database.models import Department, Organization, User
from app.infra.database.session import get_db
from app.schemas.common import PageParams
from app.schemas.orgs import DepartmentCreate, DepartmentView, OrganizationCreate, OrganizationView
from app.services.org_service import create_department, create_organization, list_organizations

router = APIRouter()


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


@router.post("/departments", response_model=DepartmentView, status_code=201)
def create_org_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Department:
    return create_department(db, payload)

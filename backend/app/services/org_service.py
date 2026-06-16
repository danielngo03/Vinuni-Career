from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.database.models import Department, Organization
from app.schemas.orgs import DepartmentCreate, OrganizationCreate


def create_organization(db: Session, payload: OrganizationCreate) -> Organization:
    org = Organization(name=payload.name.strip(), type=payload.type, metadata_json=payload.metadata)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def list_organizations(db: Session, *, limit: int = 20, offset: int = 0) -> list[Organization]:
    stmt = (
        select(Organization)
        .where(Organization.deleted_at.is_(None))
        .order_by(Organization.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def create_department(db: Session, payload: DepartmentCreate) -> Department:
    dept = Department(org_id=payload.org_id, parent_id=payload.parent_id, name=payload.name.strip())
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept

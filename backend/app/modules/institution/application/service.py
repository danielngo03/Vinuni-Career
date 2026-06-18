from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.modules.institution.api.schemas import (
    DepartmentCreate,
    IndustryCreate,
    IndustryView,
    MajorReference,
    OrganizationCreate,
    RegistrationReferenceData,
    UniversityReference,
)
from app.platform.database.models import Department, Industry, Organization, UniversityMajor
from app.shared.enum import OrgType
from app.shared.errors import AppError, ErrorCode


def registration_reference_data(
    db: Session,
    university_org_id: str | None = None,
) -> RegistrationReferenceData:
    universities = list(
        db.scalars(
            select(Organization)
            .where(
                Organization.type == OrgType.UNIVERSITY,
                Organization.deleted_at.is_(None),
                exists(
                    select(UniversityMajor.id).where(
                        UniversityMajor.org_id == Organization.id,
                        UniversityMajor.is_active.is_(True),
                    )
                ),
                exists(
                    select(Industry.id).where(
                        Industry.university_org_id == Organization.id,
                        Industry.is_active.is_(True),
                    )
                ),
            )
            .order_by(Organization.name)
        )
    )
    allowed_ids = {item.id for item in universities}
    selected_ids = {university_org_id} if university_org_id in allowed_ids else allowed_ids
    majors = list(
        db.scalars(
            select(UniversityMajor)
            .where(
                UniversityMajor.org_id.in_(selected_ids),
                UniversityMajor.is_active.is_(True),
            )
            .order_by(UniversityMajor.major_name)
        )
    )
    industries = list(
        db.scalars(
            select(Industry)
            .where(
                Industry.university_org_id.in_(selected_ids),
                Industry.is_active.is_(True),
            )
            .order_by(Industry.name_vi)
        )
    )
    return RegistrationReferenceData(
        universities=[
            UniversityReference(id=item.id, name=item.name) for item in universities
        ],
        majors=[
            MajorReference(
                id=item.id,
                university_org_id=item.org_id,
                code=item.major_code,
                name=item.major_name,
            )
            for item in majors
        ],
        industries=[IndustryView.model_validate(item) for item in industries],
    )


def create_industry(
    db: Session,
    *,
    university_org_id: str,
    payload: IndustryCreate,
) -> Industry:
    university = db.get(Organization, university_org_id)
    if not university or university.type != OrgType.UNIVERSITY:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="A university organization is required",
            status_code=400,
        )
    if payload.parent_id:
        parent = db.get(Industry, payload.parent_id)
        if not parent or parent.university_org_id != university_org_id:
            raise AppError(
                code=ErrorCode.BAD_REQUEST,
                message="Parent industry belongs to another university",
                status_code=400,
            )
    item = Industry(
        university_org_id=university_org_id,
        parent_id=payload.parent_id,
        code=payload.code,
        name_vi=payload.name_vi,
        name_en=payload.name_en,
        description=payload.description,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


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

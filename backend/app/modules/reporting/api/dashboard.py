from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.access.api.identity import get_active_identity
from app.modules.reporting.application.dashboard_service import (
    get_partner_dashboard,
    get_student_dashboard,
    get_university_dashboard,
)
from app.modules.reporting.schemas import PartnerDashboard, StudentDashboard, UniversityDashboard
from app.platform.database.models import User, UserOrgRole
from app.platform.database.session import get_db

router = APIRouter()


@router.get("/student", response_model=StudentDashboard)
def student_dashboard(
    identity: UserOrgRole = Depends(get_active_identity),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StudentDashboard:
    return get_student_dashboard(db, current_user, identity.id)


@router.get("/partner", response_model=PartnerDashboard)
def partner_dashboard(
    identity: UserOrgRole = Depends(get_active_identity),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PartnerDashboard:
    return get_partner_dashboard(db, current_user, identity.id)


@router.get("/university", response_model=UniversityDashboard)
def university_dashboard(
    identity: UserOrgRole = Depends(get_active_identity),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UniversityDashboard:
    return get_university_dashboard(db, current_user, identity.id)

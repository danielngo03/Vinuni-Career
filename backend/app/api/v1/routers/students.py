from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.infra.database.models import StudentProfile, User
from app.infra.database.session import get_db
from app.schemas.common import PageParams
from app.schemas.students import StudentProfileCreate, StudentProfileView
from app.services.student_service import create_student_profile, list_student_profiles

router = APIRouter()
DEMO_STUDENTS_DIR = Path(__file__).resolve().parents[4] / ".data" / "demo" / "students"


class DemoStudentProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    age: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    university: str | None = Field(default=None, max_length=160)
    major: str | None = Field(default=None, max_length=160)
    graduation_year: str | None = Field(default=None, max_length=20)
    linkedin: str | None = Field(default=None, max_length=240)
    github: str | None = Field(default=None, max_length=240)
    portfolio: str | None = Field(default=None, max_length=240)
    bio: str | None = Field(default=None, max_length=1000)
    profile_highlights: dict[str, Any] | None = None


@router.post("", response_model=StudentProfileView, status_code=201)
def create_profile(
    payload: StudentProfileCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> StudentProfile:
    return create_student_profile(db, payload)


@router.get("", response_model=list[StudentProfileView])
def list_profiles(
    page: PageParams = Depends(),
    org_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[StudentProfile]:
    return list_student_profiles(db, org_id, limit=page.limit, offset=page.offset)


@router.patch("/demo/{student_id}/profile", response_model=dict[str, Any])
def update_demo_student_profile(
    student_id: str,
    payload: DemoStudentProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ensure_demo_student_access(current_user, student_id)
    path = DEMO_STUDENTS_DIR / f"{student_id}.json"
    student = _read_json(path) if path.exists() else {"student_id": student_id}

    profile = dict(student.get("profile", {}))
    updates = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in payload.model_dump().items()
        if value is not None and key != "profile_highlights"
    }
    profile.update(updates)
    student["profile"] = profile
    if payload.profile_highlights is not None:
        student["profile_highlights"] = payload.profile_highlights
    if updates.get("full_name"):
        student["name"] = updates["full_name"]
    student.setdefault("name", profile.get("full_name") or student_id)
    student.setdefault("skills", {})
    student.setdefault("metadata", {})

    _write_json(path, student)
    if updates.get("full_name"):
        _sync_demo_user_full_name(db, student_id, updates["full_name"])
    return student


def _ensure_demo_student_access(user: User, student_id: str) -> None:
    if user.email.startswith("student_"):
        linked_id = _source_id_from_full_name(user.full_name) or user.email
        if linked_id != student_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _source_id_from_full_name(full_name: str) -> str | None:
    if not full_name.endswith(")"):
        return None
    marker = full_name.rfind("(")
    if marker == -1:
        return None
    return full_name[marker + 1 : -1]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _sync_demo_user_full_name(db: Session, student_id: str, full_name: str) -> None:
    suffix = f"({student_id})"
    for user in db.query(User).all():
        if user.email == student_id or user.full_name.endswith(suffix):
            user.full_name = f"{full_name} {suffix}"
    db.commit()

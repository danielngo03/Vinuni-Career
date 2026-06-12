"""API routes for the student profile agent."""

from __future__ import annotations

from typing import Any

from backend.src.agents.student_profile.service import summarize_student_profile
from backend.src.core.auth import DemoUser, require_roles
from backend.src.core.config import settings
from backend.src.models.schemas import StudentProfile, ValidationError, student_from_dict, student_to_dict
from backend.src.services.storage import JsonStudentRepository

try:
    from fastapi import APIRouter, Depends, HTTPException
except ImportError:  # pragma: no cover - used only when optional API dependency is absent.
    APIRouter = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]


saved_student_repo = JsonStudentRepository(settings.students_dir)
student_provider = saved_student_repo


def _can_access_student(student: StudentProfile, user: DemoUser) -> bool:
    if user.role == "enterprise":
        return True
    owner_user_id = student.metadata.get("owner_user_id")
    return owner_user_id == user.user_id or student.student_id == user.user_id


def _ensure_student_access(student: StudentProfile, user: DemoUser) -> None:
    if not _can_access_student(student, user):
        raise HTTPException(status_code=403, detail="Students can only access their own profile.")


def _get_student_from_provider(student_id: str) -> StudentProfile:
    for student in student_provider.list_profiles():
        if student.student_id == student_id:
            return student
    raise FileNotFoundError(f"Student not found: {student_id}")


if APIRouter is not None:
    router = APIRouter(prefix="/agents/student-profile", tags=["student_profile"])

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"agent": "student_profile", "status": "ok"}

    @router.post("/students")
    def create_student(
        payload: dict[str, Any],
        user: DemoUser = Depends(require_roles("student")),
    ) -> dict[str, Any]:
        try:
            metadata = payload.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["owner_user_id"] = user.user_id
            student = student_from_dict(payload)
            return student_to_dict(saved_student_repo.save(student))
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/students")
    def list_students(
        user: DemoUser = Depends(require_roles("student", "enterprise")),
    ) -> list[dict[str, Any]]:
        if user.role == "enterprise":
            return [student_to_dict(student) for student in student_provider.list_profiles()]
        return [
            student_to_dict(student)
            for student in saved_student_repo.list_profiles()
            if _can_access_student(student, user)
        ]

    @router.get("/students/mock")
    def list_mock_students(_user: DemoUser = Depends(require_roles("enterprise"))) -> list[dict[str, Any]]:
        return [
            student_to_dict(student)
            for student in saved_student_repo.list_profiles()
            if student.metadata.get("is_mock") is True
        ]

    @router.get("/students/{student_id}")
    def get_student(
        student_id: str,
        user: DemoUser = Depends(require_roles("student", "enterprise")),
    ) -> dict[str, Any]:
        try:
            student = _get_student_from_provider(student_id)
            _ensure_student_access(student, user)
            return student_to_dict(student)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.patch("/students/{student_id}")
    def update_student(
        student_id: str,
        payload: dict[str, Any],
        user: DemoUser = Depends(require_roles("student")),
    ) -> dict[str, Any]:
        try:
            current = saved_student_repo.get(student_id)
            _ensure_student_access(current, user)
            payload["student_id"] = student_id
            metadata = payload.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["owner_user_id"] = user.user_id
            student = student_from_dict(payload)
            return student_to_dict(saved_student_repo.save(student))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete("/students/{student_id}")
    def delete_student(
        student_id: str,
        user: DemoUser = Depends(require_roles("student")),
    ) -> dict[str, str]:
        try:
            student = saved_student_repo.get(student_id)
            _ensure_student_access(student, user)
            saved_student_repo.delete(student_id)
            return {"status": "deleted", "student_id": student_id}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/students/{student_id}/summary")
    def summarize_student(
        student_id: str,
        top_n: int = 3,
        user: DemoUser = Depends(require_roles("student", "enterprise")),
    ) -> dict[str, Any]:
        try:
            student = _get_student_from_provider(student_id)
            _ensure_student_access(student, user)
            return summarize_student_profile(student, top_n=max(1, min(top_n, 10)))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
else:
    router = None

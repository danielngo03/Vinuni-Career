"""API routes for CV parsing and saved student profiles."""

from __future__ import annotations

from typing import Any

from backend.src.core.auth import DemoUser, require_roles
from backend.src.core.config import settings
from backend.src.models.schemas import ValidationError, student_from_dict, student_to_dict
from backend.src.services.cv_parser import cv_parse_metadata_to_dict, parse_cv_text_with_metadata
from backend.src.services.document_reader import extract_text_from_bytes
from backend.src.services.storage import JsonStudentRepository

try:
    from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
except ImportError:  # pragma: no cover - used only when optional API dependency is absent.
    APIRouter = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]


student_repo = JsonStudentRepository(settings.students_dir)


def _ensure_student_owner(student_data: dict[str, Any], user: DemoUser) -> None:
    if user.role != "student":
        return
    metadata = student_data.get("metadata", {})
    owner_user_id = metadata.get("owner_user_id") if isinstance(metadata, dict) else None
    if owner_user_id and owner_user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Students can only access their own profile.")


if APIRouter is not None:
    router = APIRouter(tags=["cv_analysis"])

    @router.get("/agents/cv-analysis/health")
    def health() -> dict[str, str]:
        return {"agent": "cv_analysis", "status": "ok"}

    @router.post("/students/cv/parse")
    def parse_cv(
        payload: dict[str, Any],
        _user: DemoUser = Depends(require_roles("student")),
    ) -> dict[str, Any]:
        try:
            result = parse_cv_text_with_metadata(str(payload.get("raw_text", "")))
            response = student_to_dict(result.student)
            response["_parser"] = cv_parse_metadata_to_dict(result.metadata)
            return response
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/students/cv/parse-upload")
    async def parse_uploaded_cv(
        file: UploadFile = File(...),
        _user: DemoUser = Depends(require_roles("student")),
    ) -> dict[str, Any]:
        try:
            content = await file.read()
            raw_text = extract_text_from_bytes(file.filename or "cv.txt", content)
            result = parse_cv_text_with_metadata(raw_text)
            response = student_to_dict(result.student)
            response["_parser"] = cv_parse_metadata_to_dict(result.metadata)
            return response
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/students")
    def save_student(
        payload: dict[str, Any],
        user: DemoUser = Depends(require_roles("student")),
    ) -> dict[str, Any]:
        try:
            metadata = payload.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["owner_user_id"] = user.user_id
            student = student_from_dict(payload)
            return student_to_dict(student_repo.save(student))
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/students")
    def list_students(_user: DemoUser = Depends(require_roles("enterprise"))) -> list[dict[str, Any]]:
        return [student_to_dict(student) for student in student_repo.list_profiles()]

    @router.get("/students/{student_id}")
    def get_student(
        student_id: str,
        user: DemoUser = Depends(require_roles("student", "enterprise")),
    ) -> dict[str, Any]:
        try:
            student_data = student_to_dict(student_repo.get(student_id))
            _ensure_student_owner(student_data, user)
            return student_data
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.delete("/students/{student_id}")
    def delete_student(
        student_id: str,
        user: DemoUser = Depends(require_roles("student")),
    ) -> dict[str, str]:
        try:
            student_data = student_to_dict(student_repo.get(student_id))
            _ensure_student_owner(student_data, user)
            student_repo.delete(student_id)
            return {"status": "deleted", "student_id": student_id}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
else:
    router = None

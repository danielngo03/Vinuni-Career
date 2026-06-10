"""API routes for the student profile agent."""

from __future__ import annotations

from typing import Any

from backend.src.agents.student_profile.service import summarize_student_profile
from backend.src.core.config import settings
from backend.src.services.storage import MockStudentProfileProvider

try:
    from fastapi import APIRouter, HTTPException
except ImportError:  # pragma: no cover - used only when optional API dependency is absent.
    APIRouter = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]


student_provider = MockStudentProfileProvider(settings.mock_students_path)


if APIRouter is not None:
    router = APIRouter(prefix="/agents/student-profile", tags=["student_profile"])

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"agent": "student_profile", "status": "ok"}

    @router.get("/students/{student_id}/summary")
    def summarize_student(student_id: str, top_n: int = 3) -> dict[str, Any]:
        for student in student_provider.list_profiles():
            if student.student_id == student_id:
                return summarize_student_profile(student, top_n=max(1, min(top_n, 10)))
        raise HTTPException(status_code=404, detail=f"Student not found: {student_id}")
else:
    router = None

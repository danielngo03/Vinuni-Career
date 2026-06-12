"""FastAPI app composition for backend agents."""

from __future__ import annotations

from typing import Any

try:
    from fastapi import FastAPI
except ImportError:  # pragma: no cover - used only when optional API dependency is absent.
    FastAPI = None  # type: ignore[assignment]

from backend.src.agents.jd_matching.router import router as jd_matching_router
from backend.src.agents.cv_analysis.router import router as cv_analysis_router
from backend.src.agents.student_profile.router import router as student_profile_router
from backend.src.core.config import settings


if FastAPI is not None:
    app = FastAPI(title="Corhort Backend Agents")
    app.include_router(jd_matching_router)
    app.include_router(cv_analysis_router)
    app.include_router(student_profile_router)

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": "Corhort Backend Agents",
            "status": "ok",
            "docs": "/docs",
            "demo_auth": {
                "enabled": settings.demo_auth_enabled,
                "headers": {
                    "X-Demo-Role": "student | enterprise",
                    "X-Demo-User-Id": "optional demo user id",
                },
            },
            "agents": {
                "jd_matching": {
                    "description": "Enterprise JD parsing, job management, and student matching.",
                    "health": "/agents/jd-matching/health",
                    "main_endpoints": ["/jobs", "/jobs/parse", "/jobs/{job_id}/match", "/students/mock"],
                },
                "student_profile": {
                    "description": "Student profile management, mock profile access, and skill summaries.",
                    "health": "/agents/student-profile/health",
                    "main_endpoints": [
                        "/agents/student-profile/students",
                        "/agents/student-profile/students/mock",
                        "/agents/student-profile/students/{student_id}",
                        "/agents/student-profile/students/{student_id}/summary",
                    ],
                },
                "cv_analysis": {
                    "description": "CV upload, student skill extraction, validation, and local student storage.",
                    "health": "/agents/cv-analysis/health",
                    "main_endpoints": ["/students/cv/parse", "/students/cv/parse-upload", "/students"],
                },
            },
        }

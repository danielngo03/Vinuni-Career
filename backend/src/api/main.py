"""FastAPI app composition for backend agents."""

from __future__ import annotations

from typing import Any

try:
    from fastapi import FastAPI
except ImportError:  # pragma: no cover - used only when optional API dependency is absent.
    FastAPI = None  # type: ignore[assignment]

from backend.src.agents.jd_matching.router import router as jd_matching_router
from backend.src.agents.student_profile.router import router as student_profile_router


if FastAPI is not None:
    app = FastAPI(title="Corhort Backend Agents")
    app.include_router(jd_matching_router)
    app.include_router(student_profile_router)

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": "Corhort Backend Agents",
            "status": "ok",
            "docs": "/docs",
            "agents": {
                "jd_matching": {
                    "description": "Enterprise JD parsing, job management, and student matching.",
                    "health": "/agents/jd-matching/health",
                    "main_endpoints": ["/jobs", "/jobs/parse", "/jobs/{job_id}/match", "/students/mock"],
                },
                "student_profile": {
                    "description": "Student profile summaries and skill insight endpoints.",
                    "health": "/agents/student-profile/health",
                    "main_endpoints": ["/agents/student-profile/students/{student_id}/summary"],
                },
            },
        }

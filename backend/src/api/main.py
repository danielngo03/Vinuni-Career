"""FastAPI wrapper for the enterprise JD matching module."""

from __future__ import annotations

from typing import Any

from backend.src.core.config import settings
from backend.src.models.schemas import (
    MatchThresholds,
    ValidationError,
    job_from_dict,
    job_to_dict,
    match_result_to_dict,
    student_to_dict,
)
from backend.src.services.document_reader import extract_text_from_bytes
from backend.src.services.jd_parser import parse_jd_form_with_metadata, parse_jd_text_with_metadata, parse_metadata_to_dict
from backend.src.services.matching import match_students_for_job
from backend.src.services.storage import JsonJobRepository, MockStudentProfileProvider

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
except ImportError:  # pragma: no cover - used only when optional API dependency is absent.
    FastAPI = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]


job_repo = JsonJobRepository(settings.jobs_dir)
student_provider = MockStudentProfileProvider(settings.mock_students_path)


if FastAPI is not None:
    app = FastAPI(title="Enterprise JD Matching Module")

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": "Enterprise JD Matching Module",
            "status": "ok",
            "docs": "/docs",
            "endpoints": {
                "jobs": "/jobs",
                "mock_students": "/students/mock",
            },
        }

    @app.post("/jobs/parse")
    def parse_job(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            company_id = str(payload.get("company_id", "company_demo"))
            if "form" in payload and isinstance(payload["form"], dict):
                result = parse_jd_form_with_metadata(payload["form"], company_id=company_id)
            else:
                result = parse_jd_text_with_metadata(str(payload.get("raw_text", "")), company_id=company_id)
            response = job_to_dict(result.job)
            response["_parser"] = parse_metadata_to_dict(result.metadata)
            return response
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/jobs/parse-upload")
    async def parse_uploaded_job(
        company_id: str = Form("company_demo"),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        try:
            content = await file.read()
            raw_text = extract_text_from_bytes(file.filename or "job.txt", content)
            result = parse_jd_text_with_metadata(raw_text, company_id=company_id)
            response = job_to_dict(result.job)
            response["_parser"] = parse_metadata_to_dict(result.metadata)
            return response
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/jobs")
    def create_job(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            job = job_from_dict(payload)
            return job_to_dict(job_repo.save(job))
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return [job_to_dict(job) for job in job_repo.list()]

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        try:
            return job_to_dict(job_repo.get(job_id))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.patch("/jobs/{job_id}")
    def update_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            payload["job_id"] = job_id
            job = job_from_dict(payload)
            return job_to_dict(job_repo.save(job))
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/jobs/{job_id}/open")
    def open_job(job_id: str) -> dict[str, Any]:
        try:
            return job_to_dict(job_repo.update_status(job_id, "open"))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/jobs/{job_id}/close")
    def close_job(job_id: str) -> dict[str, Any]:
        try:
            return job_to_dict(job_repo.update_status(job_id, "closed"))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/jobs/{job_id}")
    def delete_job(job_id: str) -> dict[str, str]:
        try:
            job_repo.delete(job_id)
            return {"status": "deleted", "job_id": job_id}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/students/mock")
    def list_mock_students() -> list[dict[str, Any]]:
        return [student_to_dict(student) for student in student_provider.list_profiles()]

    @app.post("/jobs/{job_id}/match")
    def match_job(job_id: str, payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            payload = payload or {}
            thresholds = MatchThresholds(
                strong_match=float(payload.get("strong_match", settings.strong_match_threshold)),
                partial_match=float(payload.get("partial_match", settings.partial_match_threshold)),
            )
            results = match_students_for_job(job_repo.get(job_id), student_provider.list_profiles(), thresholds)
            return [match_result_to_dict(result) for result in results]
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

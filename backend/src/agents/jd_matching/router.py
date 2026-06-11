"""API routes for the JD matching agent."""

from __future__ import annotations

from typing import Any

from backend.src.core.auth import DemoUser, require_roles
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
from backend.src.services.storage import (
    CombinedStudentProfileProvider,
    JsonJobRepository,
    JsonStudentRepository,
    MockStudentProfileProvider,
)

try:
    from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
except ImportError:  # pragma: no cover - used only when optional API dependency is absent.
    APIRouter = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]


job_repo = JsonJobRepository(settings.jobs_dir)
saved_student_repo = JsonStudentRepository(settings.students_dir)
mock_student_provider = MockStudentProfileProvider(settings.mock_students_path)
student_provider = CombinedStudentProfileProvider(saved_student_repo, mock_student_provider)


if APIRouter is not None:
    router = APIRouter(tags=["jd_matching"])

    @router.get("/agents/jd-matching/health")
    def health() -> dict[str, str]:
        return {"agent": "jd_matching", "status": "ok"}

    @router.post("/jobs/parse")
    def parse_job(
        payload: dict[str, Any],
        _user: DemoUser = Depends(require_roles("enterprise")),
    ) -> dict[str, Any]:
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

    @router.post("/jobs/parse-upload")
    async def parse_uploaded_job(
        company_id: str = Form("company_demo"),
        file: UploadFile = File(...),
        _user: DemoUser = Depends(require_roles("enterprise")),
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

    @router.post("/jobs")
    def create_job(
        payload: dict[str, Any],
        user: DemoUser = Depends(require_roles("enterprise")),
    ) -> dict[str, Any]:
        try:
            payload["company_id"] = user.user_id
            job = job_from_dict(payload)
            return job_to_dict(job_repo.save(job))
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/jobs")
    def list_jobs(user: DemoUser = Depends(require_roles("enterprise"))) -> list[dict[str, Any]]:
        return [job_to_dict(job) for job in job_repo.list() if job.company_id == user.user_id]

    @router.get("/jobs/open")
    def list_open_jobs(_user: DemoUser = Depends(require_roles("student", "enterprise"))) -> list[dict[str, Any]]:
        return [job_to_dict(job) for job in job_repo.list() if job.status == "open"]

    @router.get("/jobs/{job_id}")
    def get_job(
        job_id: str,
        user: DemoUser = Depends(require_roles("student", "enterprise")),
    ) -> dict[str, Any]:
        try:
            job = job_repo.get(job_id)
            if user.role == "student" and job.status != "open":
                raise HTTPException(status_code=403, detail="Students can only view open jobs.")
            if user.role == "enterprise" and job.company_id != user.user_id:
                raise HTTPException(status_code=403, detail="Enterprises can only view their own jobs.")
            return job_to_dict(job)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.patch("/jobs/{job_id}")
    def update_job(
        job_id: str,
        payload: dict[str, Any],
        user: DemoUser = Depends(require_roles("enterprise")),
    ) -> dict[str, Any]:
        try:
            current = job_repo.get(job_id)
            if current.company_id != user.user_id:
                raise HTTPException(status_code=403, detail="Enterprises can only update their own jobs.")
            payload["job_id"] = job_id
            payload["company_id"] = user.user_id
            job = job_from_dict(payload)
            return job_to_dict(job_repo.save(job))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/jobs/{job_id}/open")
    def open_job(
        job_id: str,
        user: DemoUser = Depends(require_roles("enterprise")),
    ) -> dict[str, Any]:
        try:
            current = job_repo.get(job_id)
            if current.company_id != user.user_id:
                raise HTTPException(status_code=403, detail="Enterprises can only open their own jobs.")
            return job_to_dict(job_repo.update_status(job_id, "open"))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/jobs/{job_id}/close")
    def close_job(
        job_id: str,
        user: DemoUser = Depends(require_roles("enterprise")),
    ) -> dict[str, Any]:
        try:
            current = job_repo.get(job_id)
            if current.company_id != user.user_id:
                raise HTTPException(status_code=403, detail="Enterprises can only close their own jobs.")
            return job_to_dict(job_repo.update_status(job_id, "closed"))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.delete("/jobs/{job_id}")
    def delete_job(
        job_id: str,
        user: DemoUser = Depends(require_roles("enterprise")),
    ) -> dict[str, str]:
        try:
            current = job_repo.get(job_id)
            if current.company_id != user.user_id:
                raise HTTPException(status_code=403, detail="Enterprises can only delete their own jobs.")
            job_repo.delete(job_id)
            return {"status": "deleted", "job_id": job_id}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/students/mock")
    def list_mock_students(_user: DemoUser = Depends(require_roles("enterprise"))) -> list[dict[str, Any]]:
        return [student_to_dict(student) for student in mock_student_provider.list_profiles()]

    @router.post("/jobs/{job_id}/match")
    def match_job(
        job_id: str,
        payload: dict[str, Any] | None = None,
        user: DemoUser = Depends(require_roles("enterprise")),
    ) -> list[dict[str, Any]]:
        try:
            payload = payload or {}
            thresholds = MatchThresholds(
                strong_match=float(payload.get("strong_match", settings.strong_match_threshold)),
                partial_match=float(payload.get("partial_match", settings.partial_match_threshold)),
            )
            job = job_repo.get(job_id)
            if job.company_id != user.user_id:
                raise HTTPException(status_code=403, detail="Enterprises can only match their own jobs.")
            results = match_students_for_job(job, student_provider.list_profiles(), thresholds)
            return [match_result_to_dict(result) for result in results]
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/students/{student_id}/match-jobs")
    def match_student_jobs(
        student_id: str,
        payload: dict[str, Any] | None = None,
        user: DemoUser = Depends(require_roles("student")),
    ) -> list[dict[str, Any]]:
        try:
            student = saved_student_repo.get(student_id)
            if student.metadata.get("owner_user_id") != user.user_id:
                raise HTTPException(status_code=403, detail="Students can only match their own profile.")
            payload = payload or {}
            thresholds = MatchThresholds(
                strong_match=float(payload.get("strong_match", settings.strong_match_threshold)),
                partial_match=float(payload.get("partial_match", settings.partial_match_threshold)),
            )
            results = []
            for job in job_repo.list():
                if job.status != "open":
                    continue
                match = match_students_for_job(job, [student], thresholds)[0]
                results.append({"job": job_to_dict(job), "match": match_result_to_dict(match)})
            return sorted(results, key=lambda item: item["match"]["match_score"], reverse=True)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
else:
    router = None

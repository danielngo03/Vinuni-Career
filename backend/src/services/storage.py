"""Local JSON repositories used for the demo module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.src.models.schemas import (
    JobRequirementProfile,
    StudentProfile,
    ValidationError,
    job_from_dict,
    job_to_dict,
    student_from_dict,
)


class JsonJobRepository:
    def __init__(self, jobs_dir: Path) -> None:
        self.jobs_dir = jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def save(self, job: JobRequirementProfile) -> JobRequirementProfile:
        path = self._path(job.job_id)
        path.write_text(json.dumps(job_to_dict(job), indent=2, ensure_ascii=False), encoding="utf-8")
        return job

    def get(self, job_id: str) -> JobRequirementProfile:
        path = self._path(job_id)
        if not path.exists():
            raise FileNotFoundError(f"Job not found: {job_id}")
        return job_from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> list[JobRequirementProfile]:
        jobs: list[JobRequirementProfile] = []
        for path in sorted(self.jobs_dir.glob("*.json")):
            jobs.append(job_from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return jobs

    def delete(self, job_id: str) -> None:
        path = self._path(job_id)
        if not path.exists():
            raise FileNotFoundError(f"Job not found: {job_id}")
        path.unlink()

    def update_status(self, job_id: str, status: str) -> JobRequirementProfile:
        if status not in {"open", "closed", "draft"}:
            raise ValidationError("Status must be draft, open, or closed.")
        job = self.get(job_id)
        job.status = status  # type: ignore[assignment]
        return self.save(job)


class MockStudentProfileProvider:
    def __init__(self, path: Path) -> None:
        self.path = path

    def list_profiles(self) -> list[StudentProfile]:
        if not self.path.exists():
            return []
        data: Any = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValidationError("Mock student profile file must contain a list.")
        return [student_from_dict(item) for item in data]

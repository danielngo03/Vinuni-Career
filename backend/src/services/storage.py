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
    student_to_dict,
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


class JsonStudentRepository:
    def __init__(self, students_dir: Path) -> None:
        self.students_dir = students_dir
        self.students_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, student_id: str) -> Path:
        return self.students_dir / f"{student_id}.json"

    def save(self, student: StudentProfile) -> StudentProfile:
        path = self._path(student.student_id)
        path.write_text(json.dumps(student_to_dict(student), indent=2, ensure_ascii=False), encoding="utf-8")
        return student

    def get(self, student_id: str) -> StudentProfile:
        path = self._path(student_id)
        if not path.exists():
            raise FileNotFoundError(f"Student not found: {student_id}")
        return student_from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_profiles(self) -> list[StudentProfile]:
        students: list[StudentProfile] = []
        for path in sorted(self.students_dir.glob("*.json")):
            students.append(student_from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return students

    def delete(self, student_id: str) -> None:
        path = self._path(student_id)
        if not path.exists():
            raise FileNotFoundError(f"Student not found: {student_id}")
        path.unlink()


class CombinedStudentProfileProvider:
    def __init__(self, saved_repo: JsonStudentRepository, mock_provider: MockStudentProfileProvider) -> None:
        self.saved_repo = saved_repo
        self.mock_provider = mock_provider

    def list_profiles(self) -> list[StudentProfile]:
        profiles_by_id: dict[str, StudentProfile] = {}
        for student in self.mock_provider.list_profiles():
            profiles_by_id[student.student_id] = student
        for student in self.saved_repo.list_profiles():
            profiles_by_id[student.student_id] = student
        return list(profiles_by_id.values())

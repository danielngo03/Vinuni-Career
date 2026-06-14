import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.src.agents.jd_matching import router as jd_matching_router
from backend.src.models.schemas import job_from_dict, student_from_dict
from backend.src.services import cv_reviewer
from backend.src.services.cv_reviewer import review_student_against_job
from backend.src.services.storage import JsonJobRepository, JsonStudentRepository


class CvReviewerServiceTests(unittest.TestCase):
    def test_fallback_review_returns_missing_skills_and_keywords(self):
        original_get_provider = cv_reviewer.get_llm_provider
        cv_reviewer.get_llm_provider = lambda: (_ for _ in ()).throw(RuntimeError("no provider"))
        try:
            job = job_from_dict(
                {
                    "job_id": "job_review",
                    "company_id": "company_demo",
                    "title": "Backend Intern",
                    "status": "open",
                    "employment_type": "internship",
                    "location": "HCMC",
                    "salary_range": "3-5M",
                    "benefits": [],
                    "skills": {
                        "Python": {"required_level": 7, "importance": 0.9, "required": True},
                        "SQL": {"required_level": 7, "importance": 0.8, "required": True},
                        "Docker": {"required_level": 5, "importance": 0.5, "required": False},
                    },
                    "raw_text": "Backend Intern requiring Python, SQL, Docker, REST API, and testing.",
                }
            )
            student = student_from_dict(
                {
                    "student_id": "student_review",
                    "name": "Review Student",
                    "skills": {
                        "Python": {"score": 8, "confidence": 0.9, "evidence": ["Built a Python API"]},
                    },
                    "metadata": {"cv_text_excerpt": "Built a Python API for a coursework project."},
                }
            )

            review = review_student_against_job(student, job)
        finally:
            cv_reviewer.get_llm_provider = original_get_provider

        self.assertTrue(review["_reviewer"]["fallback_used"])
        self.assertEqual(review["match"]["match_status"], "not_match")
        self.assertIn("SQL", {item["skill"] for item in review["missing_skills"]})
        self.assertIn("Docker", review["missing_keywords"])


class CvReviewerRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_path = Path(self.temp_dir.name)
        self.jobs_dir = base_path / "jobs"
        self.students_dir = base_path / "students"

        self.original_saved_job_repo = jd_matching_router.saved_job_repo
        self.original_job_repo = jd_matching_router.job_repo
        self.original_saved_student_repo = jd_matching_router.saved_student_repo
        self.original_student_provider = jd_matching_router.student_provider
        self.original_get_provider = cv_reviewer.get_llm_provider

        self.job_repo = JsonJobRepository(self.jobs_dir)
        self.student_repo = JsonStudentRepository(self.students_dir)
        self.job_repo.save(
            job_from_dict(
                {
                    "job_id": "job_review_route",
                    "company_id": "company_demo",
                    "title": "Data Intern",
                    "status": "open",
                    "employment_type": "internship",
                    "location": "HCMC",
                    "salary_range": "3-5M",
                    "benefits": [],
                    "skills": {
                        "Python": {"required_level": 7, "importance": 0.9, "required": True},
                        "SQL": {"required_level": 7, "importance": 0.8, "required": True},
                    },
                    "raw_text": "Data intern requiring Python and SQL.",
                }
            )
        )
        self.student_repo.save(
            student_from_dict(
                {
                    "student_id": "student_owner",
                    "name": "Owner Student",
                    "skills": {
                        "Python": {"score": 8, "confidence": 0.9, "evidence": ["Python project"]},
                    },
                    "metadata": {"owner_user_id": "student_owner"},
                }
            )
        )

        jd_matching_router.saved_job_repo = self.job_repo
        jd_matching_router.job_repo = self.job_repo
        jd_matching_router.saved_student_repo = self.student_repo
        jd_matching_router.student_provider = self.student_repo
        cv_reviewer.get_llm_provider = lambda: (_ for _ in ()).throw(RuntimeError("no provider"))

        app = FastAPI()
        app.include_router(jd_matching_router.router)
        self.client = TestClient(app)

    def tearDown(self):
        jd_matching_router.saved_job_repo = self.original_saved_job_repo
        jd_matching_router.job_repo = self.original_job_repo
        jd_matching_router.saved_student_repo = self.original_saved_student_repo
        jd_matching_router.student_provider = self.original_student_provider
        cv_reviewer.get_llm_provider = self.original_get_provider
        self.temp_dir.cleanup()

    def test_review_endpoint_requires_student_owner(self):
        owner_headers = {"X-Demo-Role": "student", "X-Demo-User-Id": "student_owner"}
        other_headers = {"X-Demo-Role": "student", "X-Demo-User-Id": "student_other"}

        ok = self.client.post(
            "/students/student_owner/jobs/job_review_route/review",
            json={"use_llm": False},
            headers=owner_headers,
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["student_id"], "student_owner")

        forbidden = self.client.post(
            "/students/student_owner/jobs/job_review_route/review",
            json={"use_llm": False},
            headers=other_headers,
        )
        self.assertEqual(forbidden.status_code, 403)


if __name__ == "__main__":
    unittest.main()

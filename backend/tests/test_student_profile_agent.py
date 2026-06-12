import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.src.agents.student_profile import router as student_profile_router
from backend.src.agents.student_profile.service import summarize_student_profile
from backend.src.models.schemas import student_from_dict
from backend.src.services.storage import JsonStudentRepository


class StudentProfileAgentTests(unittest.TestCase):
    def test_summary_ranks_top_skills(self):
        student = student_from_dict(
            {
                "student_id": "student_test",
                "name": "Test Student",
                "skills": {
                    "Python": {"score": 8, "confidence": 0.9, "evidence": ["API project"]},
                    "SQL": {"score": 6, "confidence": 0.8, "evidence": ["DB project"]},
                    "React": {"score": 7, "confidence": 0.7, "evidence": ["Frontend project"]},
                },
                "metadata": {"major": "Computer Science", "year": 3},
            }
        )

        summary = summarize_student_profile(student, top_n=2)

        self.assertEqual(summary["student_id"], "student_test")
        self.assertEqual(summary["average_skill_score"], 7.0)
        self.assertEqual([skill["name"] for skill in summary["top_skills"]], ["Python", "React"])
        self.assertIn("Python, React", summary["summary"])


class StudentProfileRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_path = Path(self.temp_dir.name)
        self.students_dir = base_path / "students"
        self.original_saved_repo = student_profile_router.saved_student_repo
        self.original_student_provider = student_profile_router.student_provider

        saved_repo = JsonStudentRepository(self.students_dir)
        saved_repo.save(
            student_from_dict(
                {
                    "student_id": "mock_student",
                    "name": "Mock Student",
                    "skills": {
                        "Python": {"score": 8, "confidence": 0.9, "evidence": ["Mock project"]},
                    },
                    "metadata": {"is_mock": True},
                }
            )
        )
        student_profile_router.saved_student_repo = saved_repo
        student_profile_router.student_provider = saved_repo

        app = FastAPI()
        app.include_router(student_profile_router.router)
        self.client = TestClient(app)

    def tearDown(self):
        student_profile_router.saved_student_repo = self.original_saved_repo
        student_profile_router.student_provider = self.original_student_provider
        self.temp_dir.cleanup()

    def test_student_profile_crud_uses_owner_and_enterprise_rules(self):
        student_headers = {"X-Demo-Role": "student", "X-Demo-User-Id": "student_owner"}
        other_student_headers = {"X-Demo-Role": "student", "X-Demo-User-Id": "student_other"}
        enterprise_headers = {"X-Demo-Role": "enterprise", "X-Demo-User-Id": "company_demo"}
        payload = {
            "student_id": "student_owner_profile",
            "name": "Owner Student",
            "skills": {
                "Python": {"score": 7, "confidence": 0.8, "evidence": ["API coursework"]},
            },
        }

        created = self.client.post("/agents/student-profile/students", json=payload, headers=student_headers)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["metadata"]["owner_user_id"], "student_owner")

        listed = self.client.get("/agents/student-profile/students", headers=enterprise_headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            {student["student_id"] for student in listed.json()},
            {"mock_student", "student_owner_profile"},
        )

        forbidden = self.client.get(
            "/agents/student-profile/students/student_owner_profile",
            headers=other_student_headers,
        )
        self.assertEqual(forbidden.status_code, 403)

        updated_payload = {
            "name": "Owner Student",
            "skills": {
                "Python": {"score": 9, "confidence": 0.9, "evidence": ["Capstone API"]},
            },
        }
        updated = self.client.patch(
            "/agents/student-profile/students/student_owner_profile",
            json=updated_payload,
            headers=student_headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["skills"]["Python"]["score"], 9.0)
        self.assertEqual(updated.json()["metadata"]["owner_user_id"], "student_owner")

        deleted = self.client.delete(
            "/agents/student-profile/students/student_owner_profile",
            headers=student_headers,
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"status": "deleted", "student_id": "student_owner_profile"})


if __name__ == "__main__":
    unittest.main()

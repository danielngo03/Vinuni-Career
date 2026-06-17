import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.src.agents.cv_analysis import router as cv_analysis_router
from backend.src.api.main import app
from backend.src.models.schemas import student_from_dict
from backend.src.services import cv_parser
from backend.src.services.storage import JsonStudentRepository


class CvAnalysisTests(unittest.TestCase):
    def test_fallback_cv_parser_extracts_student_profile(self):
        original_get_provider = cv_parser.get_llm_provider
        cv_parser.get_llm_provider = lambda: (_ for _ in ()).throw(RuntimeError("no provider"))
        try:
            result = cv_parser.parse_cv_text_with_metadata(
                """
                Nguyen Van A
                Email: a@example.com
                Major: Computer Science
                Projects:
                Built a FastAPI backend using Python and SQL.
                Developed React dashboard with JavaScript.
                """
            )
        finally:
            cv_parser.get_llm_provider = original_get_provider

        self.assertEqual(result.student.name, "Nguyen Van A")
        self.assertEqual(result.student.metadata["email"], "a@example.com")
        self.assertIn("Python", result.student.skills)
        self.assertIn("SQL", result.student.skills)
        self.assertTrue(result.metadata.fallback_used)

    def test_cv_form_parser_builds_student_profile(self):
        original_get_provider = cv_parser.get_llm_provider
        cv_parser.get_llm_provider = lambda: (_ for _ in ()).throw(RuntimeError("no provider"))
        try:
            result = cv_parser.parse_cv_form_with_metadata(
                {
                    "name": "Tran Thi B",
                    "email": "b@example.com",
                    "major": "Information Systems",
                    "year": "Second year",
                    "skills": "Python, SQL, React",
                    "projects": "Built a React dashboard with Python API and SQL reports.",
                }
            )
        finally:
            cv_parser.get_llm_provider = original_get_provider

        self.assertEqual(result.student.name, "Tran Thi B")
        self.assertEqual(result.student.metadata["email"], "b@example.com")
        self.assertEqual(result.student.metadata["major"], "Information Systems")
        self.assertIn("Python", result.student.skills)
        self.assertIn("React", result.student.skills)
        self.assertTrue(result.metadata.fallback_used)

    def test_cv_parser_preserves_self_rated_skill_signals(self):
        original_get_provider = cv_parser.get_llm_provider
        cv_parser.get_llm_provider = lambda: (_ for _ in ()).throw(RuntimeError("no provider"))
        try:
            result = cv_parser.parse_cv_text_with_metadata(
                """
                Le Minh
                Skills:
                Python ★★★★☆
                SQL 80%
                React Advanced
                Docker ▰▰▰▱▱
                C++ 4/5
                """
            )
        finally:
            cv_parser.get_llm_provider = original_get_provider

        python_rating = result.student.skills["Python"].self_rating
        sql_rating = result.student.skills["SQL"].self_rating
        react_rating = result.student.skills["React"].self_rating
        docker_rating = result.student.skills["Docker"].self_rating
        cpp_rating = result.student.skills["C++"].self_rating

        self.assertEqual(python_rating["source"], "stars")
        self.assertEqual(python_rating["normalized_score"], 8)
        self.assertEqual(sql_rating["source"], "percent")
        self.assertEqual(sql_rating["normalized_score"], 8)
        self.assertEqual(react_rating["source"], "level")
        self.assertEqual(react_rating["normalized_score"], 8)
        self.assertEqual(docker_rating["source"], "bar")
        self.assertEqual(docker_rating["normalized_score"], 6)
        self.assertEqual(cpp_rating["source"], "slash")
        self.assertEqual(cpp_rating["normalized_score"], 8)
        self.assertIn("self_rating_note", result.student.metadata)

    def test_cv_upload_response_includes_extracted_text_for_review(self):
        original_parse = cv_analysis_router.parse_cv_text_with_metadata
        cv_analysis_router.parse_cv_text_with_metadata = lambda raw_text: cv_parser.parse_cv_text_with_metadata(
            raw_text,
            use_llm=False,
        )
        try:
            client = TestClient(app)
            response = client.post(
                "/students/cv/parse-upload",
                headers={
                    "X-Demo-Role": "student",
                    "X-Demo-User-Id": "student_test",
                },
                files={
                    "file": (
                        "cv.txt",
                        b"Le Minh\nSkills:\nPython 8/10\nProjects:\nBuilt a Python API.",
                        "text/plain",
                    )
                },
            )
        finally:
            cv_analysis_router.parse_cv_text_with_metadata = original_parse

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("_raw_text", payload)
        self.assertIn("Python 8/10", payload["_raw_text"])

    def test_student_repository_saves_and_reads_profiles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = JsonStudentRepository(Path(temp_dir))
            student = student_from_dict(
                {
                    "student_id": "student_saved",
                    "name": "Saved Student",
                    "skills": {
                        "Python": {"score": 8, "confidence": 0.9, "evidence": ["API project"]},
                    },
                    "metadata": {"major": "Computer Science"},
                }
            )

            repo.save(student)
            loaded = repo.get("student_saved")

            self.assertEqual(loaded.name, "Saved Student")
            self.assertEqual(len(repo.list_profiles()), 1)


if __name__ == "__main__":
    unittest.main()

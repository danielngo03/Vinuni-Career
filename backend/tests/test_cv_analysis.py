import tempfile
import unittest
from pathlib import Path

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

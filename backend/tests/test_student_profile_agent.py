import unittest

from backend.src.agents.student_profile.service import summarize_student_profile
from backend.src.models.schemas import student_from_dict


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


if __name__ == "__main__":
    unittest.main()

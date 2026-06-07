import unittest

from backend.src.models.schemas import MatchThresholds, job_from_dict, match_result_to_dict, student_from_dict
from backend.src.services.matching import match_students_for_job


class MatchingTests(unittest.TestCase):
    def test_ranks_students_and_blocks_strong_when_required_skill_missing(self):
        job = job_from_dict(
            {
                "job_id": "job_test",
                "company_id": "company_test",
                "title": "Backend Intern",
                "status": "open",
                "employment_type": "internship",
                "location": "HCMC",
                "salary_range": "3-5M",
                "benefits": [],
                "skills": {
                    "Python": {"required_level": 7, "importance": 0.9, "required": True},
                    "SQL": {"required_level": 7, "importance": 0.8, "required": True},
                    "Docker": {"required_level": 5, "importance": 0.4, "required": False},
                },
            }
        )
        strong_student = student_from_dict(
            {
                "student_id": "student_1",
                "name": "Strong Student",
                "skills": {
                    "Python": {"score": 8, "confidence": 0.9, "evidence": []},
                    "SQL": {"score": 8, "confidence": 0.9, "evidence": []},
                    "Docker": {"score": 5, "confidence": 0.8, "evidence": []},
                },
            }
        )
        missing_sql_student = student_from_dict(
            {
                "student_id": "student_2",
                "name": "Missing SQL Student",
                "skills": {
                    "Python": {"score": 9, "confidence": 0.9, "evidence": []},
                    "Docker": {"score": 5, "confidence": 0.8, "evidence": []},
                },
            }
        )

        results = match_students_for_job(job, [missing_sql_student, strong_student])
        serialized = [match_result_to_dict(result) for result in results]

        self.assertEqual(serialized[0]["student_id"], "student_1")
        self.assertEqual(serialized[0]["match_status"], "strong_match")
        self.assertNotEqual(serialized[1]["match_status"], "strong_match")
        self.assertIn("SQL", serialized[1]["missing_or_weak_skills"])

    def test_thresholds_are_configurable(self):
        job = job_from_dict(
            {
                "job_id": "job_test",
                "company_id": "company_test",
                "title": "Python Intern",
                "status": "open",
                "employment_type": "internship",
                "location": "HCMC",
                "salary_range": "3-5M",
                "benefits": [],
                "skills": {
                    "Python": {"required_level": 10, "importance": 1.0, "required": False},
                },
            }
        )
        student = student_from_dict(
            {
                "student_id": "student_1",
                "name": "Python Student",
                "skills": {"Python": {"score": 8, "confidence": 0.9, "evidence": []}},
            }
        )

        default_result = match_students_for_job(job, [student])[0]
        strict_result = match_students_for_job(
            job,
            [student],
            MatchThresholds(strong_match=0.9, partial_match=0.85),
        )[0]

        self.assertEqual(default_result.match_status, "strong_match")
        self.assertEqual(strict_result.match_status, "not_match")

    def test_closed_job_cannot_be_matched(self):
        job = job_from_dict(
            {
                "job_id": "job_test",
                "company_id": "company_test",
                "title": "Closed Job",
                "status": "closed",
                "employment_type": "internship",
                "location": "HCMC",
                "salary_range": "3-5M",
                "benefits": [],
                "skills": {
                    "Python": {"required_level": 7, "importance": 1.0, "required": True},
                },
            }
        )

        with self.assertRaisesRegex(ValueError, "status = open"):
            match_students_for_job(job, [])


if __name__ == "__main__":
    unittest.main()

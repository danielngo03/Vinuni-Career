import sys
import types
import unittest
from types import SimpleNamespace

from backend.src.services import jd_parser


class JdParserTests(unittest.TestCase):
    def test_parser_uses_selected_llm_provider(self):
        calls = {}

        class FakeProvider:
            name = "custom"
            model = "custom-test"
            is_configured = True

            def generate(self, prompt):
                calls["prompt"] = prompt
                return """
                {
                  "job_id": "job_provider",
                  "company_id": "company_fake",
                  "title": "AI Intern",
                  "status": "draft",
                  "employment_type": "internship",
                  "location": "Remote",
                  "salary_range": "unspecified",
                  "benefits": [],
                  "skills": {
                    "LLM": {
                      "required_level": 7,
                      "importance": 0.8,
                      "required": true
                    }
                  },
                  "raw_text": "placeholder"
                }
                """

        original_get_provider = jd_parser.get_llm_provider
        jd_parser.get_llm_provider = lambda: FakeProvider()
        try:
            result = jd_parser.parse_jd_text_with_metadata("Title: AI Intern", "company_test")
        finally:
            jd_parser.get_llm_provider = original_get_provider

        self.assertIn("Title: AI Intern", calls["prompt"])
        self.assertEqual(result.job.company_id, "company_test")
        self.assertEqual(result.job.job_id, "job_provider")
        self.assertEqual(result.metadata.parser_mode, "custom")
        self.assertEqual(result.metadata.model, "custom-test")
        self.assertTrue(result.metadata.used_llm)
        self.assertFalse(result.metadata.fallback_used)

    def test_gemini_parser_uses_current_google_genai_client(self):
        calls = {}

        class FakeModels:
            def generate_content(self, model, contents):
                calls["model"] = model
                calls["contents"] = contents
                return SimpleNamespace(
                    text="""
                    {
                      "job_id": "job_fake",
                      "company_id": "company_fake",
                      "title": "Backend Intern",
                      "status": "draft",
                      "employment_type": "internship",
                      "location": "HCMC",
                      "salary_range": "unspecified",
                      "benefits": [],
                      "skills": {
                        "Python": {
                          "required_level": 7,
                          "importance": 0.9,
                          "required": true
                        }
                      },
                      "raw_text": "placeholder"
                    }
                    """
                )

        class FakeClient:
            def __init__(self, api_key):
                calls["api_key"] = api_key
                self.models = FakeModels()

            def close(self):
                calls["closed"] = True

        fake_genai = types.ModuleType("google.genai")
        fake_genai.Client = FakeClient
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai

        original_google = sys.modules.get("google")
        original_genai = sys.modules.get("google.genai")
        original_settings = jd_parser.settings
        sys.modules["google"] = fake_google
        sys.modules["google.genai"] = fake_genai
        jd_parser.settings = SimpleNamespace(gemini_api_key="test-key", gemini_model="gemini-test")
        try:
            parsed = jd_parser._parse_with_gemini("Title: Backend Intern", "company_test")
        finally:
            jd_parser.settings = original_settings
            if original_google is None:
                sys.modules.pop("google", None)
            else:
                sys.modules["google"] = original_google
            if original_genai is None:
                sys.modules.pop("google.genai", None)
            else:
                sys.modules["google.genai"] = original_genai

        self.assertEqual(calls["api_key"], "test-key")
        self.assertEqual(calls["model"], "gemini-test")
        self.assertIn("Title: Backend Intern", calls["contents"])
        self.assertTrue(calls["closed"])
        self.assertEqual(parsed["company_id"], "company_test")
        self.assertEqual(parsed["job_id"], "job_fake")


if __name__ == "__main__":
    unittest.main()

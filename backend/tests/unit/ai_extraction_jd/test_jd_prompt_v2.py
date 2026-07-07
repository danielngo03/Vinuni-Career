from app.ai.prompts.jd_extraction import v2


def test_prompt_version_and_schema_fields_present():
    assert v2.PROMPT_VERSION == 2
    for token in ("candidate_requirements", "salary_mode", "experience_mode",
                  "seniority_level", "application_deadline", "is_jd"):
        assert token in v2.TEXT_SYSTEM_PROMPT
        assert token in v2.VISION_SYSTEM_PROMPT


def test_user_message_truncates_long_text():
    msg = v2.build_text_user_message("x" * 9000)
    assert "document truncated" in msg
    assert len(msg) < 9000 + 500

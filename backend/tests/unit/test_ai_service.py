from __future__ import annotations

from app.modules.ai_operations.application.legacy_ai_service import mask_pii, match_cv_to_job


def test_mask_pii_redacts_email_phone_and_possible_name():
    masked, entities = mask_pii("Nguyen Van A\nEmail: a@example.com\nPhone: 0912345678")

    assert "a@example.com" not in masked
    assert "0912345678" not in masked
    assert "[REDACTED_EMAIL]" in masked
    assert "[REDACTED_PHONE]" in masked
    assert {entity["type"] for entity in entities} >= {"EMAIL", "PHONE", "POSSIBLE_NAME"}


def test_match_cv_to_job_prefers_shared_skills():
    result = match_cv_to_job(
        "Python FastAPI PostgreSQL Redis Docker",
        "We need Python, FastAPI, PostgreSQL and Docker for backend APIs.",
    )

    assert result.score > 70
    assert {"python", "fastapi", "postgresql", "docker"}.issubset(set(result.matched_skills))

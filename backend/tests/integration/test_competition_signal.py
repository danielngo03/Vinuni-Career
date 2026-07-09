"""Integration tests for the competition level signal feature.

Covers:
  - Happy path: visible/active job returns a well-formed signal dict.
  - 404 for draft (unpublished) and non-existent jobs.
  - Guest principal (GUEST) can access public-visibility jobs.
  - Authenticated student gets the same data (no field is auth-gated for this read).
  - AI unavailable: offline provider → explanation=None, ai_explanation_available=False.
  - No raw application count by default (show_application_count not set in settings).
  - Application count exposed when partner opted in via settings.
  - No AI provider/model/token leakage in response.
  - Signal response includes expected keys and valid level value.
"""

from __future__ import annotations

import json
import uuid

import pytest
from app.modules.opportunities.application import (
    competition_service,
    job_service,
    moderation_service,
)
from app.modules.opportunities.domain.models import Job
from app.modules.recruitment.domain.models import Application
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import GUEST
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin

# --------------------------------------------------------------------------- #
# Forbidden terms — must not appear in any user-facing response               #
# --------------------------------------------------------------------------- #

_FORBIDDEN = [
    "openrouter",
    "openai",
    "anthropic",
    "claude",
    "gpt-4",
    "gemini",
    "deepseek",
    "chat_cheap",
    "reasoning_cheap",
    "model_alias",
    "prompt_tokens",
    "completion_tokens",
    "storage_path",
    "storage_key",
    "confidence",
    "embedding",
]

_VALID_LEVELS = {"low", "medium", "high", "very_high"}
_VALID_LABELS = {"Thấp", "Trung bình", "Cao", "Rất cao"}


def _assert_no_leakage(payload: object) -> None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for term in _FORBIDDEN:
        assert term not in blob, f"leaked term in response: {term!r}"


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _job_payload(**over) -> dict:
    base = {
        "title": "Backend Engineer",
        "description": "Build REST APIs using Python.",
        "requirements": "Python, FastAPI required.",
        "benefits": None,
        "employment_type": "full_time",
        "location_type": "onsite",
        "location_city": "Hanoi",
        "location_country": "Vietnam",
        "required_skills": ["python", "fastapi", "postgresql"],
        "preferred_skills": ["docker"],
        "experience_min_years": None,
        "experience_max_years": None,
        "degree_required": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "headcount": 2,
        "application_deadline": None,
        "visibility": "public",
    }
    base.update(over)
    return base


async def _publish_job(db: AsyncSession, *, partner_principal, uni_principal, **over) -> uuid.UUID:
    """Create, submit, and approve a job (active + moderation_approved)."""
    created = await job_service.create_job(
        db, principal=partner_principal, payload=_job_payload(**over), ctx=CTX
    )
    job_id = uuid.UUID(created["id"])
    await job_service.submit_job(db, principal=partner_principal, job_id=job_id, ctx=CTX)
    await moderation_service.approve_job(db, principal=uni_principal, job_id=job_id, ctx=CTX)
    return job_id


async def _insert_application(
    db: AsyncSession, *, job_id: uuid.UUID, org_id: uuid.UUID, status: str = "submitted"
) -> None:
    """Insert a bare application row for count tests (bypasses apply_service)."""
    app = Application(
        id=uuid.uuid4(),
        job_id=job_id,
        applicant_id=uuid.uuid4(),  # synthetic student id
        org_id=org_id,
        status=status,
    )
    db.add(app)
    await db.commit()


# --------------------------------------------------------------------------- #
# Happy path                                                                   #
# --------------------------------------------------------------------------- #


async def test_visible_job_returns_signal(db_session: AsyncSession) -> None:
    _u, org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, partner_principal=partner, uni_principal=uni)

    result = await competition_service.competition_signal(
        db_session, principal=GUEST, job_id=job_id
    )

    assert result["level"] in _VALID_LEVELS
    assert result["label"] in _VALID_LABELS
    assert result["basis"] == "estimated"
    assert "jd_complexity_score" in result
    assert isinstance(result["jd_complexity_score"], int)
    assert "updated_at" in result
    assert "ai_explanation_available" in result
    # Offline provider → AI enrichment degrades cleanly
    assert result["ai_explanation_available"] is False
    assert result["explanation"] is None


async def test_response_keys_all_present(db_session: AsyncSession) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, partner_principal=partner, uni_principal=uni)

    result = await competition_service.competition_signal(
        db_session, principal=GUEST, job_id=job_id
    )

    for key in (
        "level",
        "label",
        "explanation",
        "ai_explanation_available",
        "basis",
        "jd_complexity_score",
        "application_count",
        "updated_at",
    ):
        assert key in result, f"missing key: {key!r}"


# --------------------------------------------------------------------------- #
# 404 cases                                                                    #
# --------------------------------------------------------------------------- #


async def test_nonexistent_job_raises_404(db_session: AsyncSession) -> None:
    with pytest.raises(ResourceNotFoundError):
        await competition_service.competition_signal(
            db_session, principal=GUEST, job_id=uuid.uuid4()
        )


async def test_draft_job_is_not_visible(db_session: AsyncSession) -> None:
    """A draft (unpublished) job is indistinguishable from missing → 404."""
    _u, _org, partner = await make_org_with_admin(db_session)

    created = await job_service.create_job(
        db_session, principal=partner, payload=_job_payload(), ctx=CTX
    )
    job_id = uuid.UUID(created["id"])
    # Do NOT submit or approve — job remains a draft.

    with pytest.raises(ResourceNotFoundError):
        await competition_service.competition_signal(db_session, principal=GUEST, job_id=job_id)


async def test_pending_review_job_is_not_visible(db_session: AsyncSession) -> None:
    """A job in pending_review (submitted, not yet approved) is not public."""
    _u, _org, partner = await make_org_with_admin(db_session)

    created = await job_service.create_job(
        db_session, principal=partner, payload=_job_payload(), ctx=CTX
    )
    job_id = uuid.UUID(created["id"])
    await job_service.submit_job(db_session, principal=partner, job_id=job_id, ctx=CTX)
    # Not approved → still invisible to public.

    with pytest.raises(ResourceNotFoundError):
        await competition_service.competition_signal(db_session, principal=GUEST, job_id=job_id)


# --------------------------------------------------------------------------- #
# RBAC: guest and authenticated principals                                     #
# --------------------------------------------------------------------------- #


async def test_guest_can_access_public_visibility_job(db_session: AsyncSession) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(
        db_session,
        partner_principal=partner,
        uni_principal=uni,
        visibility="public",
    )

    # GUEST should succeed for public visibility
    result = await competition_service.competition_signal(
        db_session, principal=GUEST, job_id=job_id
    )
    assert result["level"] in _VALID_LEVELS


async def test_authenticated_student_can_access_job(db_session: AsyncSession) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, partner_principal=partner, uni_principal=uni)

    _su, student = await make_student(db_session)
    result = await competition_service.competition_signal(
        db_session, principal=student, job_id=job_id
    )
    assert result["level"] in _VALID_LEVELS


# --------------------------------------------------------------------------- #
# AI unavailable degradation (offline provider — default in tests)             #
# --------------------------------------------------------------------------- #


async def test_offline_provider_degrades_cleanly(db_session: AsyncSession) -> None:
    """Under the default offline provider: explanation=None, ai_explanation_available=False."""
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, partner_principal=partner, uni_principal=uni)

    result = await competition_service.competition_signal(
        db_session, principal=GUEST, job_id=job_id
    )

    # Deterministic fields are always present
    assert result["level"] in _VALID_LEVELS
    assert result["jd_complexity_score"] is not None
    # AI enrichment degrades
    assert result["explanation"] is None
    assert result["ai_explanation_available"] is False


# --------------------------------------------------------------------------- #
# Application count privacy                                                    #
# --------------------------------------------------------------------------- #


async def test_application_count_hidden_by_default(db_session: AsyncSession) -> None:
    """Raw application count is NOT returned unless partner opted in."""
    _u, org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, partner_principal=partner, uni_principal=uni)

    # Insert an application to make the count non-zero
    await _insert_application(db_session, job_id=job_id, org_id=org.id)

    result = await competition_service.competition_signal(
        db_session, principal=GUEST, job_id=job_id
    )

    # By default, show_application_count is not set → count is None in response
    assert result["application_count"] is None


async def test_application_count_exposed_when_opted_in(db_session: AsyncSession) -> None:
    """Raw application count IS returned when partner opted in via settings."""
    _u, org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, partner_principal=partner, uni_principal=uni)

    # Insert 2 active applications
    await _insert_application(db_session, job_id=job_id, org_id=org.id, status="submitted")
    await _insert_application(db_session, job_id=job_id, org_id=org.id, status="under_review")

    # Opt the partner in by updating job.settings directly
    job = (await db_session.execute(select(Job).where(Job.id == job_id))).scalar_one()
    job.settings = {**job.settings, "show_application_count": True}
    await db_session.commit()

    result = await competition_service.competition_signal(
        db_session, principal=GUEST, job_id=job_id
    )

    assert result["application_count"] == 2


async def test_rejected_applications_not_counted(db_session: AsyncSession) -> None:
    """Rejected and withdrawn applications do not contribute to the count."""
    _u, org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, partner_principal=partner, uni_principal=uni)

    # Insert one active and two terminal applications
    await _insert_application(db_session, job_id=job_id, org_id=org.id, status="submitted")
    await _insert_application(db_session, job_id=job_id, org_id=org.id, status="rejected")
    await _insert_application(db_session, job_id=job_id, org_id=org.id, status="withdrawn")

    # Opt in so we can inspect the count
    job = (await db_session.execute(select(Job).where(Job.id == job_id))).scalar_one()
    job.settings = {**job.settings, "show_application_count": True}
    await db_session.commit()

    result = await competition_service.competition_signal(
        db_session, principal=GUEST, job_id=job_id
    )

    # Only the "submitted" application counts
    assert result["application_count"] == 1


# --------------------------------------------------------------------------- #
# Level correctness (deterministic, end-to-end with DB)                       #
# --------------------------------------------------------------------------- #


async def test_internship_no_exp_few_skills_is_low(db_session: AsyncSession) -> None:
    """Entry internship with 2 skills and no applicants → low competition."""
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(
        db_session,
        partner_principal=partner,
        uni_principal=uni,
        employment_type="internship",
        required_skills=["python", "git"],
        experience_min_years=None,
    )

    result = await competition_service.competition_signal(
        db_session, principal=GUEST, job_id=job_id
    )

    # jd_complexity: 0 + 0 - 10 = -10; app_contribution=0; raw=-10 → low
    assert result["level"] == "low"
    assert result["jd_complexity_score"] == -10


async def test_signal_reflects_experience_requirement(db_session: AsyncSession) -> None:
    """Senior full-time job with many skills has higher complexity than entry."""
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    entry_job_id = await _publish_job(
        db_session,
        partner_principal=partner,
        uni_principal=uni,
        title="Entry Role",
        employment_type="full_time",
        required_skills=["python"],
        experience_min_years=None,
    )
    _u2, _org2, partner2 = await make_org_with_admin(db_session, display_name="Corp B")
    _uu2, _uorg2, uni2 = await make_org_with_admin(
        db_session, org_type="university", display_name="Uni B"
    )
    senior_job_id = await _publish_job(
        db_session,
        partner_principal=partner2,
        uni_principal=uni2,
        title="Senior Role",
        employment_type="full_time",
        required_skills=["python", "fastapi", "postgresql", "redis", "kafka", "aws", "docker"],
        experience_min_years=7,
    )

    entry_result = await competition_service.competition_signal(
        db_session, principal=GUEST, job_id=entry_job_id
    )
    senior_result = await competition_service.competition_signal(
        db_session, principal=GUEST, job_id=senior_job_id
    )

    assert senior_result["jd_complexity_score"] > entry_result["jd_complexity_score"]


# --------------------------------------------------------------------------- #
# Provider / model / token leakage guard                                       #
# --------------------------------------------------------------------------- #


async def test_no_ai_provider_leakage_in_response(db_session: AsyncSession) -> None:
    """No provider/model/token internals must appear in the response payload."""
    _u, _org, partner = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, partner_principal=partner, uni_principal=uni)

    result = await competition_service.competition_signal(
        db_session, principal=GUEST, job_id=job_id
    )

    _assert_no_leakage(result)

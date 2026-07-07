"""Logged-in student job intelligence slice (E35: B-535..B-540).

Covers: strong/good/possible/weak fit labels, no-active-CV state, stale CV,
low-signal competition (few applications), closed/hidden job -> 404,
non-student persona -> 403, already-applied apply-readiness, and a
provider/model/token/other-applicant leakage assertion.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.documents.domain.models import CvProfile, CvSection
from app.modules.opportunities.application import (
    job_service,
    moderation_service,
    student_intelligence_service,
)
from app.modules.recruitment.domain.models import Application
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_ready_cv, make_student
from tests.org_utils import make_org_with_admin

_FORBIDDEN = [
    "openrouter", "openai", "anthropic", "claude", "gpt-4", "gemini", "deepseek",
    "chat_cheap", "reasoning_cheap", "model_alias", "prompt_tokens",
    "completion_tokens", "storage_path", "storage_key", "confidence", "embedding",
    "rank", "percentile",
]


def _assert_no_leak(payload: object) -> None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for term in _FORBIDDEN:
        assert term not in blob, f"leaked term: {term!r}"


def _job_payload(**over) -> dict:
    base = {
        "title": "Backend Intern",
        "description": "We are hiring a backend intern to build REST APIs.",
        "requirements": "Experience with Python and FastAPI is required.",
        "benefits": None,
        "employment_type": "internship",
        "location_type": "onsite",
        "location_city": "Hanoi",
        "location_country": "Vietnam",
        "required_skills": ["Python", "FastAPI"],
        "preferred_skills": ["PostgreSQL"],
        "experience_min_years": None,
        "experience_max_years": None,
        "degree_required": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "headcount": 1,
        "application_deadline": None,
        "visibility": "public",
    }
    base.update(over)
    return base


async def _create_job(db, *, publish: bool = True, **over) -> uuid.UUID:
    _u, _org, admin = await make_org_with_admin(db)
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    created = await job_service.create_job(
        db, principal=admin, payload=_job_payload(**over), ctx=CTX
    )
    jid = uuid.UUID(created["id"])
    if publish:
        await job_service.submit_job(db, principal=admin, job_id=jid, ctx=CTX)
        await moderation_service.approve_job(db, principal=uni, job_id=jid, ctx=CTX)
    return jid


async def _make_cv(db, student, *, title="My CV") -> dict:
    # Student intelligence / fit reads only committed library CVs (``ready``), so
    # finalize the CV (seeds a header name so the non-empty gate passes). Sections
    # are read live, so callers may keep seeding content afterward.
    return await make_ready_cv(db, student=student, title=title)


async def _seed(db, cv_id, section_type, items) -> None:
    sections = (
        await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id)))
    ).scalars().all()
    target = next(s for s in sections if s.section_type == section_type)
    target.content_json = {"items": items}
    await db.commit()


async def _age_cv(db, cv_id, *, days: int) -> None:
    old = datetime.now(tz=UTC) - timedelta(days=days)
    cv = (
        await db.execute(select(CvProfile).where(CvProfile.id == uuid.UUID(cv_id)))
    ).scalar_one()
    cv.last_edited_at = old
    sections = (
        await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id)))
    ).scalars().all()
    for s in sections:
        s.updated_at = old
    await db.commit()


async def _build_strong_cv(db, student, *, title="Strong CV") -> str:
    cv = await _make_cv(db, student, title=title)
    await _seed(db, cv["id"], "skills", [{"text": "Python, FastAPI, PostgreSQL, SQL"}])
    await _seed(
        db, cv["id"], "experience",
        [{"text": "Built REST APIs with Python and FastAPI at a startup."}],
    )
    await _seed(db, cv["id"], "summary", [{"text": "Backend engineering intern."}])
    await _seed(db, cv["id"], "education", [{"text": "BSc Computer Science, VinUniversity."}])
    return cv["id"]


# --------------------------------------------------------------------------- #
# Happy path: strong fit                                                      #
# --------------------------------------------------------------------------- #


async def test_strong_fit_happy_path(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None,
    )
    assert out["job_id"] == str(job_id)
    assert out["best_cv_id"] == cv_id
    assert out["fit"]["status"] == "scored"
    assert out["fit"]["label"] in {"strong_fit", "good_fit"}
    assert out["fit"]["bands"] is not None
    assert "Python" in out["fit"]["matched_evidence"]
    assert isinstance(out["fit"]["improvement_actions"], list)
    assert out["competition"]["applicant_quality_bucket"] == "unknown"
    assert out["apply_readiness"]["ready"] is True
    assert any(a["action"] == "apply" for a in out["next_actions"])
    _assert_no_leak(out)


async def test_weak_fit_maps_to_weak_label_and_improvement_actions(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student, title="Empty CV")
    job_id = await _create_job(db_session)

    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=uuid.UUID(cv["id"]),
    )
    assert out["fit"]["label"] == "weak_fit"
    assert out["fit"]["improvement_actions"]
    assert out["learning_gaps"]
    assert out["learning_gaps"][0]["skill"]
    _assert_no_leak(out)


# --------------------------------------------------------------------------- #
# No active CV                                                                 #
# --------------------------------------------------------------------------- #


async def test_no_active_cv_state(db_session) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)

    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None,
    )
    assert out["fit"]["status"] == "no_active_cv"
    assert out["best_cv_id"] is None
    assert out["apply_readiness"]["ready"] is False
    assert out["apply_readiness"]["blocked_reason"] == "no_active_cv"
    assert any(a["action"] == "improve_cv" for a in out["next_actions"])


# --------------------------------------------------------------------------- #
# Stale CV                                                                     #
# --------------------------------------------------------------------------- #


async def test_stale_cv_surfaces_in_fit(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    await _age_cv(db_session, cv_id, days=75)
    job_id = await _create_job(db_session)

    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None,
    )
    assert out["fit"]["stale"] is True


# --------------------------------------------------------------------------- #
# Closed / hidden job -> 404                                                   #
# --------------------------------------------------------------------------- #


async def test_hidden_or_missing_job_returns_404(db_session) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)

    draft_id = await _create_job(db_session, publish=False)
    with pytest.raises(ResourceNotFoundError):
        await student_intelligence_service.student_intelligence_for_job(
            db_session, principal=student, job_id=draft_id, cv_id=None,
        )

    with pytest.raises(ResourceNotFoundError):
        await student_intelligence_service.student_intelligence_for_job(
            db_session, principal=student, job_id=uuid.uuid4(), cv_id=None,
        )


# --------------------------------------------------------------------------- #
# Non-student persona -> 403 (privacy/RBAC edge case)                         #
# --------------------------------------------------------------------------- #


async def test_non_student_persona_is_forbidden(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    job_id = await _create_job(db_session)

    with pytest.raises(PermissionDeniedError):
        await student_intelligence_service.student_intelligence_for_job(
            db_session, principal=partner, job_id=job_id, cv_id=None,
        )


# --------------------------------------------------------------------------- #
# Low-signal competition (few applications)                                   #
# --------------------------------------------------------------------------- #


async def test_low_application_volume_is_low_signal_competition(db_session) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None,
    )
    assert out["competition"]["signal"] == "low_signal"
    assert out["competition"]["score"] is None
    assert out["competition"]["label"] is None
    assert out["competition"]["guidance"]


# --------------------------------------------------------------------------- #
# Already-applied apply readiness                                             #
# --------------------------------------------------------------------------- #


async def test_already_applied_blocks_apply_readiness(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, _org, partner = await make_org_with_admin(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    app = Application(
        id=uuid.uuid4(),
        job_id=job_id,
        applicant_id=student.user_id,
        org_id=uuid.uuid4(),
        status="submitted",
    )
    db_session.add(app)
    await db_session.commit()

    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None,
    )
    assert out["apply_readiness"]["already_applied"] is True
    assert out["apply_readiness"]["ready"] is False
    assert out["apply_readiness"]["blocked_reason"] == "already_applied"
    assert any(
        a["action"] == "apply" and a["ready"] is False for a in out["next_actions"]
    )


# --------------------------------------------------------------------------- #
# Deadline freshness                                                           #
# --------------------------------------------------------------------------- #


async def test_closing_soon_deadline_bucket(db_session) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    deadline = datetime.now(tz=UTC) + timedelta(days=5)
    job_id = await _create_job(db_session, application_deadline=deadline)

    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None,
    )
    assert out["competition"]["deadline_freshness"] == "closing_soon"


# --------------------------------------------------------------------------- #
# Selected CV must belong to caller (invalid cv_id falls back to best)         #
# --------------------------------------------------------------------------- #


async def test_invalid_cv_id_falls_back_to_best(db_session) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=uuid.uuid4(),
    )
    assert out["selected_cv_id"] is None
    assert out["fit"]["status"] == "scored"

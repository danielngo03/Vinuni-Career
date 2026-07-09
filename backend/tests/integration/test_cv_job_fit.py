"""CV-to-job fit scoring + recommendation slice (offline provider, SQLite).

Covers: deterministic reproducibility, ranking a clearly-better CV first, the
>60-day stale flag, 0-active-CVs -> empty results (not 404), a closed/hidden job
-> 404, the AI-unavailable degraded state under the default offline provider, a
vague JD -> low_signal, and a provider/model/token leakage assertion.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.ai.cv import job_fit
from app.modules.documents.application import job_fit_service
from app.modules.documents.domain.models import CvProfile, CvSection
from app.modules.opportunities.application import job_service, moderation_service
from app.shared.exceptions import ResourceNotFoundError
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_ready_cv, make_student
from tests.org_utils import make_org_with_admin

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


def _assert_no_leak(payload: object) -> None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for term in _FORBIDDEN:
        assert term not in blob, f"leaked term: {term}"


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
    """Create a CV and finalize it into the library (``ready``).

    Job-fit only scores committed library CVs (design spec 2026-07-05), so tests
    that expect a CV to be scored must go through finalize. ``make_ready_cv`` seeds
    a header name and finalizes; the returned detail is the finalized CV. Sections
    are read live at match time, so tests may keep seeding content AFTER this.
    """

    return await make_ready_cv(db, student=student, title=title)


async def _seed(db, cv_id, section_type, items) -> None:
    # Test shortcut: set section content directly. A REAL section edit bumps
    # cv.version (which invalidates the cached fit rows AND the stored matching
    # snapshot); mirror that here by bumping the version so job-fit reads the
    # freshly-seeded content instead of a pre-seed snapshot.
    cv = (await db.execute(select(CvProfile).where(CvProfile.id == uuid.UUID(cv_id)))).scalar_one()
    sections = (
        (await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id))))
        .scalars()
        .all()
    )
    target = next(s for s in sections if s.section_type == section_type)
    target.content_json = {"items": items}
    cv.version += 1
    await db.commit()


async def _age_cv(db, cv_id, *, days: int) -> None:
    """Push the CV's content timestamps into the past so it reads as stale."""

    old = datetime.now(tz=UTC) - timedelta(days=days)
    cv = (await db.execute(select(CvProfile).where(CvProfile.id == uuid.UUID(cv_id)))).scalar_one()
    cv.last_edited_at = old
    sections = (
        (await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id))))
        .scalars()
        .all()
    )
    for s in sections:
        s.updated_at = old
    await db.commit()


async def _build_strong_cv(db, student, *, title="Strong CV") -> str:
    cv = await _make_cv(db, student, title=title)
    await _seed(db, cv["id"], "skills", [{"text": "Python, FastAPI, PostgreSQL, SQL"}])
    await _seed(
        db,
        cv["id"],
        "experience",
        [{"text": "Built REST APIs with Python and FastAPI at a startup."}],
    )
    await _seed(db, cv["id"], "summary", [{"text": "Backend engineering intern."}])
    await _seed(db, cv["id"], "education", [{"text": "BSc Computer Science, VinUniversity."}])
    return cv["id"]


# --------------------------------------------------------------------------- #
# Deterministic reproducibility                                                #
# --------------------------------------------------------------------------- #


async def test_scores_are_deterministic(db_session) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    first = await job_fit_service.job_fit_for_job(db_session, principal=student, job_id=job_id)
    second = await job_fit_service.job_fit_for_job(db_session, principal=student, job_id=job_id)
    assert [r["score"] for r in first["results"]] == [r["score"] for r in second["results"]]
    assert first["results"][0]["bands"] == second["results"][0]["bands"]
    assert first["recommended_cv_id"] == second["recommended_cv_id"]


# --------------------------------------------------------------------------- #
# Ranking: a clearly-better CV is recommended                                  #
# --------------------------------------------------------------------------- #


async def test_better_cv_ranks_first_and_is_recommended(db_session) -> None:
    _u, student = await make_student(db_session)
    strong_id = await _build_strong_cv(db_session, student)
    weak = await _make_cv(db_session, student, title="Empty CV")
    job_id = await _create_job(db_session)

    out = await job_fit_service.job_fit_for_job(db_session, principal=student, job_id=job_id)
    assert out["recommended_cv_id"] == strong_id
    assert out["results"][0]["cv_id"] == strong_id
    scores = {r["cv_id"]: r["score"] for r in out["results"]}
    assert scores[strong_id] > scores[weak["id"]]
    strong = next(r for r in out["results"] if r["cv_id"] == strong_id)
    assert "Python" in strong["matched_skills"]
    assert out["signal"] == "ok"
    _assert_no_leak(out)


# --------------------------------------------------------------------------- #
# Stale flag at > 60 days                                                      #
# --------------------------------------------------------------------------- #


async def test_stale_flag_when_older_than_threshold(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    await _age_cv(db_session, cv_id, days=75)
    job_id = await _create_job(db_session)

    out = await job_fit_service.job_fit_for_job(db_session, principal=student, job_id=job_id)
    result = next(r for r in out["results"] if r["cv_id"] == cv_id)
    assert result["stale"] is True
    assert result["last_updated_days"] >= 75


async def test_fresh_cv_not_stale(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    out = await job_fit_service.job_fit_for_job(db_session, principal=student, job_id=job_id)
    result = next(r for r in out["results"] if r["cv_id"] == cv_id)
    assert result["stale"] is False


# --------------------------------------------------------------------------- #
# Edge states                                                                  #
# --------------------------------------------------------------------------- #


async def test_no_active_cvs_returns_empty_not_404(db_session) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)

    out = await job_fit_service.job_fit_for_job(db_session, principal=student, job_id=job_id)
    assert out["results"] == []
    assert out["recommended_cv_id"] is None
    assert out["ai_explanation_available"] is False
    assert out["job"]["title"] == "Backend Intern"


async def test_archived_cv_is_excluded(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    cv = (
        await db_session.execute(select(CvProfile).where(CvProfile.id == uuid.UUID(cv_id)))
    ).scalar_one()
    cv.status = "archived"
    await db_session.commit()
    job_id = await _create_job(db_session)

    out = await job_fit_service.job_fit_for_job(db_session, principal=student, job_id=job_id)
    assert out["results"] == []


async def test_hidden_or_missing_job_returns_404(db_session) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)

    # Unpublished (draft) job is not discoverable by a student.
    draft_id = await _create_job(db_session, publish=False)
    with pytest.raises(ResourceNotFoundError):
        await job_fit_service.job_fit_for_job(db_session, principal=student, job_id=draft_id)

    # Entirely unknown job id.
    with pytest.raises(ResourceNotFoundError):
        await job_fit_service.job_fit_for_job(db_session, principal=student, job_id=uuid.uuid4())


# --------------------------------------------------------------------------- #
# AI-unavailable degraded state (default offline provider)                     #
# --------------------------------------------------------------------------- #


async def test_offline_provider_returns_results_without_explanation(db_session) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    out = await job_fit_service.job_fit_for_job(db_session, principal=student, job_id=job_id)
    assert out["ai_explanation_available"] is False
    assert all(r["explanation"] is None for r in out["results"])
    assert out["results"]  # deterministic results still present
    _assert_no_leak(out)


# --------------------------------------------------------------------------- #
# Vague JD -> low_signal (pure scorer)                                         #
# --------------------------------------------------------------------------- #


def test_vague_jd_is_low_signal() -> None:
    job = {
        "title": "Role",
        "required_skills": [],
        "preferred_skills": [],
        "jd_text": "Role.",
        "location_type": "remote",
    }
    cv = job_fit.CvInput(cv_id="x", title="X", language="en", sections=[], last_updated_days=0)
    out = job_fit.evaluate(job, [cv], stale_days=60)
    assert out.signal == "low_signal"


def test_rich_jd_is_ok_signal() -> None:
    job = {
        "title": "Backend Intern",
        "required_skills": ["Python", "FastAPI"],
        "preferred_skills": ["PostgreSQL"],
        "jd_text": "Build REST APIs.",
        "location_type": "remote",
    }
    out = job_fit.evaluate(job, [], stale_days=60)
    assert out.signal == "ok"

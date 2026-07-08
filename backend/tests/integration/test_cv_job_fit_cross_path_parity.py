"""Cross-path parity + empty-edge tests for the CV-JD matcher (offline).

Pins the 2026-07-07 projection-drift fix: the SAME (VN CV, EN JD) pair must
produce the SAME score / recommended CV / gap set through all three fit surfaces —

  * ``job_fit_service.job_fit_for_job``            (detail / store)
  * ``job_fit_batch_service.batch_fit_for_jobs``   (job-card badges)
  * ``job_search_service._attach_student_fit``     (discovery cards)

Before the fix the discovery projection OMITTED ``cv_language_required`` (and the
internal ``version`` stamp), so a VN CV vs an ``en``-required JD produced a
DIFFERENT gap set on the discovery card than on the detail/batch paths. All paths
run OFFLINE here (no real provider), so the cross-lingual augmentation is OFF for
all three — this isolates the projection alignment, not translation.
"""
from __future__ import annotations

import uuid

from app.modules.documents.application import job_fit_batch_service, job_fit_service
from app.modules.opportunities.application import job_search_service
from app.modules.opportunities.domain.models import Job
from sqlalchemy import select

from tests.documents_utils import make_student
from tests.integration.test_cv_job_fit import _create_job, _make_cv, _seed


class _FakeRedis:
    """Minimal in-memory Redis for the batch cache (get/setex only)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self._data[key] = value


async def _build_vn_cv(db, student, *, title="CV Tiếng Việt") -> str:
    """A Vietnamese CV (language='vi') with VN skills/experience/summary/education."""
    cv = await _make_cv(db, student, title=title)
    await _seed(db, cv["id"], "skills", [{"text": "Python, FastAPI, SQL"}])
    await _seed(
        db, cv["id"], "experience",
        [{"text": "Xây dựng REST API bằng Python và FastAPI tại một công ty khởi nghiệp."}],
    )
    await _seed(db, cv["id"], "summary", [{"text": "Thực tập sinh kỹ thuật backend."}])
    await _seed(db, cv["id"], "education", [{"text": "Cử nhân Khoa học Máy tính, VinUniversity."}])
    # Mark the CV's language as Vietnamese so an ``en``-required JD raises the
    # soft "CV in English preferred" gap.
    from app.modules.documents.domain.models import CvProfile

    profile = (
        await db.execute(select(CvProfile).where(CvProfile.id == uuid.UUID(cv["id"])))
    ).scalar_one()
    profile.language = "vi"
    await db.commit()
    return cv["id"]


# --------------------------------------------------------------------------- #
# Cross-path parity                                                            #
# --------------------------------------------------------------------------- #

async def test_same_score_and_gaps_across_detail_batch_discovery(db_session) -> None:
    _user, student = await make_student(db_session)
    cv_id = await _build_vn_cv(db_session, student)
    # JD requires an English CV — the VN CV must surface the language gap on EVERY
    # path (this is exactly what the discovery projection used to drop).
    job_id = await _create_job(db_session, cv_language_required="en")

    # 1. Detail / store path.
    detail = await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id
    )
    detail_best = detail["results"][0]

    # 2. Batch / job-card path.
    batch = await job_fit_batch_service.batch_fit_for_jobs(
        db_session, _FakeRedis(), principal=student, job_ids=[job_id]
    )
    batch_entry = batch[str(job_id)]

    # 3. Discovery-card path.
    job = (
        await db_session.execute(select(Job).where(Job.id == job_id))
    ).scalar_one()
    items = await job_search_service._attach_student_fit(
        db_session,
        principal=student,
        jobs=[job],
        items=[{"id": str(job_id)}],
    )
    disc = items[0]["student_fit"]

    # --- Score parity across all three paths. ---
    assert detail["results"][0]["score"] == batch_entry["score"] == disc["score"]

    # --- Recommended CV parity. ---
    assert (
        detail["recommended_cv_id"]
        == batch_entry["recommended_cv_id"]
        == disc["recommended_cv_id"]
        == cv_id
    )

    # --- Signal parity. ---
    assert detail["signal"] == batch_entry["signal"] == disc["signal"]

    # --- Gap parity: the language gap must be present + counted identically. ---
    assert any("English" in g for g in detail_best["gaps"])
    # Discovery's gap_count must equal the detail path's gap count (the drift bug
    # made discovery under-count by omitting the language gap).
    assert disc["gap_count"] == len(detail_best["gaps"])


# --------------------------------------------------------------------------- #
# Empty-edge: no skills, no sections -> no crash, low_signal propagates        #
# --------------------------------------------------------------------------- #

async def test_empty_jd_and_empty_cv_no_crash_low_signal(db_session) -> None:
    _user, student = await make_student(db_session)
    # A CV with NO skills section (only an empty summary), and one with zero
    # meaningful content — both must score without crashing.
    empty_cv = await _make_cv(db_session, student, title="Empty CV")
    await _seed(db_session, empty_cv["id"], "summary", [])

    # JD with empty required/preferred skill lists (valid quality otherwise).
    job_id = await _create_job(
        db_session,
        required_skills=[],
        preferred_skills=[],
        description=(
            "We are hiring a general team member to support day-to-day operations "
            "and collaborate across the company on a variety of tasks."
        ),
        requirements="",
    )

    out = await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id
    )
    assert out["results"], "an active CV must still produce a result"
    assert out["results"][0]["score"] >= 0
    # A JD with no curated skills falls back to inferred terms only -> low_signal.
    assert out["signal"] == "low_signal"


async def test_evaluate_zero_sections_no_crash() -> None:
    """A CV with zero sections at all must not crash the pure scorer."""
    from app.ai.cv import job_fit

    job = {
        "id": "job",
        "title": "Engineer",
        "description": "",
        "requirements": "",
        "benefits": "",
        "experience_mode": "no_requirement",
        "required_skills": [],
        "preferred_skills": [],
    }
    cv = job_fit.CvInput(
        cv_id="cv-empty",
        title="Empty",
        language="en",
        sections=[],
        last_updated_days=1,
    )
    out = job_fit.evaluate(job, [cv], stale_days=120)
    assert out.results[0].score >= 0
    assert out.signal == "low_signal"
    assert out.results[0].matched_skills == []

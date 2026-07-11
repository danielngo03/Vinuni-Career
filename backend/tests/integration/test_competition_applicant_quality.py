"""B-587: real applicant-quality distribution + student standing bucket.

The competition read model now aggregates a PRIVACY-SAFE distribution over the
OTHER candidates who have a persisted deterministic fit score
(``documents.cv_job_fit_scores``) for the target job, plus a coarse position band
for the requesting student. Covers:

- enough scored candidates -> a real ``applicant_quality_bucket`` + a coarse
  ``student_standing_bucket``;
- below threshold -> both stay ``"unknown"`` (low signal / privacy guard);
- the requesting student's own fit rows are excluded from the pool;
- no other-applicant identity, raw score, rank, or percentile leaks into the
  payload.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from app.modules.documents.domain.models import CvJobFitScore
from app.modules.opportunities.application import competition_service
from app.modules.opportunities.domain.models import Job

from tests.documents_utils import make_student


def _now() -> datetime:
    return datetime.now(UTC)


def _make_visible_job(session) -> Job:
    now = _now()
    job = Job(
        org_id=uuid.uuid4(),
        posted_by=uuid.uuid4(),
        title="Backend Engineer",
        slug=f"slug-{uuid.uuid4().hex[:8]}",
        description="Build APIs.",
        employment_type="full_time",
        location_type="onsite",
        visibility="public",
        status="active",
        moderation_status="approved",
        published_at=now - timedelta(minutes=10),
        created_at=now - timedelta(minutes=11),
    )
    session.add(job)
    return job


def _fit_score(session, *, job_id: uuid.UUID, user_id: uuid.UUID, score: int) -> None:
    session.add(
        CvJobFitScore(
            user_id=user_id,
            cv_id=uuid.uuid4(),
            job_id=job_id,
            score=score,
            signal="ok",
            cv_version=1,
            job_version=1,
            scorer_version="test",
        )
    )


# --------------------------------------------------------------------------- #
# Pure bucket functions (deterministic, no DB)                                #
# --------------------------------------------------------------------------- #


def test_median_odd_and_even() -> None:
    assert competition_service._median([70]) == 70
    assert competition_service._median([60, 80]) == 70
    assert competition_service._median([50, 60, 90]) == 60


def test_applicant_quality_bucket_thresholds() -> None:
    assert competition_service._applicant_quality_bucket([]) == "unknown"
    # Below the minimum pool size -> unknown even if all scores are high.
    assert competition_service._applicant_quality_bucket([90, 90, 90, 90]) == "unknown"
    assert competition_service._applicant_quality_bucket([90, 85, 80, 75, 72]) == "strong"
    assert competition_service._applicant_quality_bucket([60, 55, 52, 58, 50]) == "mixed"
    assert competition_service._applicant_quality_bucket([40, 30, 45, 20, 35]) == "developing"


def test_student_standing_bucket() -> None:
    pool = [60, 62, 65, 68, 70]
    assert competition_service._student_standing_bucket(None, pool) == "unknown"
    assert competition_service._student_standing_bucket(90, [1, 2]) == "unknown"
    assert competition_service._student_standing_bucket(95, pool) == "ahead_of_most"
    assert competition_service._student_standing_bucket(64, pool) == "middle_of_pack"
    assert competition_service._student_standing_bucket(10, pool) == "behind_most"


# --------------------------------------------------------------------------- #
# Wired-up read model                                                         #
# --------------------------------------------------------------------------- #


async def test_strong_pool_and_student_ahead(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session)
    await db_session.flush()

    other_ids = [uuid.uuid4() for _ in range(6)]
    for uid, sc in zip(other_ids, [90, 88, 82, 76, 71, 68], strict=True):
        _fit_score(db_session, job_id=job.id, user_id=uid, score=sc)
    await db_session.flush()

    out = await competition_service.student_competition_intelligence(
        db_session,
        principal=student,
        job_id=job.id,
        student_fit_score=95,
    )
    assert out["applicant_quality_bucket"] == "strong"
    assert out["student_standing_bucket"] == "ahead_of_most"

    # Privacy: no other-applicant identity or exact rank/percentile leaks.
    blob = json.dumps(out, ensure_ascii=False)
    for uid in other_ids:
        assert str(uid) not in blob
    lowered = blob.lower()
    for term in ("percentile", "rank", "cv_id", "user_id", "applicant_id"):
        assert term not in lowered


async def test_below_threshold_is_unknown(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session)
    await db_session.flush()

    # Only 2 OTHER scored candidates -> below the minimum pool size.
    for sc in [80, 75]:
        _fit_score(db_session, job_id=job.id, user_id=uuid.uuid4(), score=sc)
    await db_session.flush()

    out = await competition_service.student_competition_intelligence(
        db_session,
        principal=student,
        job_id=job.id,
        student_fit_score=90,
    )
    assert out["applicant_quality_bucket"] == "unknown"
    assert out["student_standing_bucket"] == "unknown"


async def test_student_own_scores_excluded_from_pool(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session)
    await db_session.flush()

    # The student's own CV scores for this job must NOT count toward the pool.
    for sc in [95, 92, 90, 88]:
        _fit_score(db_session, job_id=job.id, user_id=student.user_id, score=sc)
    # Only 2 OTHER candidates remain -> still below threshold -> unknown.
    for sc in [70, 65]:
        _fit_score(db_session, job_id=job.id, user_id=uuid.uuid4(), score=sc)
    await db_session.flush()

    out = await competition_service.student_competition_intelligence(
        db_session,
        principal=student,
        job_id=job.id,
        student_fit_score=93,
    )
    assert out["applicant_quality_bucket"] == "unknown"
    assert out["student_standing_bucket"] == "unknown"


async def test_developing_pool_and_student_behind(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session)
    await db_session.flush()

    for sc in [45, 40, 38, 35, 30, 25]:
        _fit_score(db_session, job_id=job.id, user_id=uuid.uuid4(), score=sc)
    await db_session.flush()

    out = await competition_service.student_competition_intelligence(
        db_session,
        principal=student,
        job_id=job.id,
        student_fit_score=20,
    )
    assert out["applicant_quality_bucket"] == "developing"
    assert out["student_standing_bucket"] == "behind_most"

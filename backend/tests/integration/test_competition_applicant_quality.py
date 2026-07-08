"""WS-5 (Task B): quality-adjusted competition grounded in REAL applicants.

The competition read model now builds its applicant-quality pool from ACTUAL
active applicants joined to their immutable snapshot ``fit_score`` — NOT from
``cv_job_fit_scores`` (anyone who merely VIEWED a fit). The headline is
quality-adjusted (reads on strong-competitor density, not raw volume), NULL-fit
applicants are unknown quality (never fit 0), and every caliber band is a coarse,
privacy-safe label served from the ``job_competition_daily`` projection.

Covers:
- the pool = real applicants (a browser who only viewed a fit is NOT counted; an
  applicant IS);
- quality-adjustment (1000-style weak volume + a few strong reads lower than raw
  count implies; caliber, not volume, drives the headline);
- bands only — no raw counts / individual scores / ranks / identities in payload;
- ``low_signal`` below the min pool;
- NULL-fit applicants treated as unknown, never 0;
- projection refresh produces the same bands as a live compute;
- the AI narrative is on-demand + metered (free deterministic bands; offline
  provider degrades cleanly and charges nothing).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from app.ai.energy import service as energy_service
from app.ai.observability.models import AiBillableUsage
from app.modules.documents.domain.models import ApplicationCvSnapshot, CvJobFitScore
from app.modules.opportunities.application import (
    competition_projection_service,
    competition_service,
)
from app.modules.opportunities.domain import competition_scoring as scoring
from app.modules.opportunities.domain.models import Job
from sqlalchemy import func, select

from tests.documents_utils import make_student


def _now() -> datetime:
    return datetime.now(UTC)


def _make_visible_job(session, *, headcount: int = 1) -> Job:
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
        headcount=headcount,
        published_at=now - timedelta(minutes=10),
        created_at=now - timedelta(minutes=11),
    )
    session.add(job)
    return job


def _applicant(
    session, *, job_id: uuid.UUID, org_id: uuid.UUID, fit_score: int | None,
    status: str = "submitted",
) -> None:
    """Create one active application + its immutable snapshot carrying ``fit_score``.

    ``fit_score=None`` models an uploaded-document apply with no scoreable CV
    (UNKNOWN quality — counts toward the total, excluded from the caliber pool).
    """

    snap_id = uuid.uuid4()
    session.add(
        ApplicationCvSnapshot(
            id=snap_id,
            user_id=uuid.uuid4(),
            snapshot_json={},
            fit_score=fit_score,
            scorer_version="v1" if fit_score is not None else None,
        )
    )
    from app.modules.recruitment.domain.models import Application

    session.add(
        Application(
            id=uuid.uuid4(),
            job_id=job_id,
            applicant_id=uuid.uuid4(),
            org_id=org_id,
            status=status,
            snapshot_id=snap_id,
        )
    )


def _viewer(session, *, job_id: uuid.UUID, score: int) -> None:
    """A browser who merely VIEWED a fit (``cv_job_fit_scores``) — never applied."""

    session.add(
        CvJobFitScore(
            user_id=uuid.uuid4(),
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
# Pure scoring functions (deterministic, no DB)                               #
# --------------------------------------------------------------------------- #


def _stats(seats: int, scored: list[int], *, extra_null: int = 0) -> scoring.CompetitionStats:
    return scoring.stats_from_pool(
        seats=seats,
        active_applications=len(scored) + extra_null,
        scored_fits=scored,
    )


def test_histogram_partitions_by_caliber() -> None:
    dev, mixed, strong, top = scoring.histogram([10, 55, 72, 90, 85, 49, 70, 84])
    assert dev == 2  # 10, 49
    assert mixed == 1  # 55
    assert strong == 3  # 72, 70, 84  (70..84)
    assert top == 2  # 90, 85  (>=85)


def test_strong_applicants_excludes_weak() -> None:
    stats = _stats(1, [90, 71, 69, 40])
    assert stats.strong_applicants == 2  # 90, 71
    assert stats.scored_applicants == 4


def test_applicant_quality_bucket_thresholds() -> None:
    assert scoring.applicant_quality_bucket(_stats(1, [])) == "unknown"
    # Below the minimum pool size -> unknown even if all scores are high.
    assert scoring.applicant_quality_bucket(_stats(1, [90, 90, 90, 90])) == "unknown"
    assert scoring.applicant_quality_bucket(_stats(1, [90, 85, 80, 75, 72])) == "strong"
    assert scoring.applicant_quality_bucket(_stats(1, [60, 55, 52, 58, 50])) == "mixed"
    assert (
        scoring.applicant_quality_bucket(_stats(1, [40, 30, 45, 20, 35]))
        == "developing"
    )


def test_student_standing_bucket_thirds() -> None:
    strong_pool = _stats(1, [72, 74, 76, 80, 90])  # all strong/top
    assert scoring.student_standing_bucket(None, strong_pool) == "unknown"
    assert scoring.student_standing_bucket(90, _stats(1, [1, 2])) == "unknown"
    assert scoring.student_standing_bucket(95, strong_pool) == "ahead_of_most"
    graded = _stats(1, [55, 60, 72, 75, 90])  # mixed=2, strong=2, top=1
    assert scoring.student_standing_bucket(55, graded) == "middle_of_pack"  # 2/5
    assert scoring.student_standing_bucket(10, graded) == "behind_most"  # 0/5


def test_standing_vs_strong_thresholds() -> None:
    pool = [72, 74, 80, 85, 90]  # a real strong contingent
    assert scoring.standing_vs_strong(None, _stats(1, pool)) == "low_signal"
    # No strong pool -> nothing to stand against.
    assert scoring.standing_vs_strong(90, _stats(1, [10, 20, 30, 40, 45])) == "low_signal"
    assert scoring.standing_vs_strong(90, _stats(1, pool)) == "ahead"
    assert scoring.standing_vs_strong(72, _stats(1, pool)) == "among"
    assert scoring.standing_vs_strong(40, _stats(1, pool)) == "behind"


def test_strong_competitor_density() -> None:
    assert scoring.strong_competitor_density(_stats(1, [90, 80])) == "low_signal"
    # seats=5, 2 strong -> 0.4/seat -> few
    assert (
        scoring.strong_competitor_density(_stats(5, [90, 80, 40, 30, 20, 10]))
        == "few"
    )
    # seats=1, 2 strong of 5 -> 2/seat -> some
    assert scoring.strong_competitor_density(_stats(1, [90, 80, 40, 30, 20])) == "some"
    # seats=1, 5 strong -> 5/seat -> many
    assert scoring.strong_competitor_density(_stats(1, [90, 85, 80, 75, 72])) == "many"


def test_applicants_per_seat_band() -> None:
    assert scoring.applicants_per_seat_band(_stats(1, [90, 80])) == "low_signal"
    assert scoring.applicants_per_seat_band(_stats(5, [70] * 6)) == "low"  # 1.2/seat
    assert scoring.applicants_per_seat_band(_stats(1, [70] * 6)) == "moderate"  # 6/seat
    assert scoring.applicants_per_seat_band(_stats(1, [70] * 20)) == "high"  # 20/seat
    assert scoring.applicants_per_seat_band(_stats(1, [70] * 45)) == "very_high"


def test_quality_adjusted_level_reads_on_caliber_not_volume() -> None:
    # Volume-heavy but weak: 40 applicants, only 2 strong, 5 seats -> low headline.
    weak_volume = _stats(5, [30] * 38 + [90, 88])
    raw_weak, level_weak, basis_weak = scoring.quality_adjusted_level(weak_volume, 0)
    assert basis_weak == "applicant_caliber"
    assert level_weak == "low"

    # Fewer applicants but all strong for one seat -> much higher headline.
    strong_few = _stats(1, [90] * 20)
    raw_strong, level_strong, _ = scoring.quality_adjusted_level(strong_few, 0)
    assert raw_strong > raw_weak
    assert level_strong in ("high", "very_high")

    # Cold start (scored pool below the min) -> honest capped-volume fallback.
    cold = scoring.stats_from_pool(seats=1, active_applications=30, scored_fits=[80])
    _raw_cold, _level_cold, basis_cold = scoring.quality_adjusted_level(cold, 0)
    assert basis_cold == "application_volume"


# --------------------------------------------------------------------------- #
# Wired read model — the pool is REAL applicants, not viewers                  #
# --------------------------------------------------------------------------- #


async def test_viewers_not_counted_applicants_are(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session, headcount=3)
    await db_session.flush()

    # Six people merely VIEWED a fit (browsers) — none applied.
    for sc in [95, 92, 90, 88, 85, 80]:
        _viewer(db_session, job_id=job.id, score=sc)
    await db_session.flush()

    out = await competition_service.student_competition_intelligence(
        db_session, principal=student, job_id=job.id, student_fit_score=95,
    )
    # Viewers do NOT populate the applicant-quality pool.
    assert out["applicant_quality_bucket"] == "unknown"
    assert out["strong_competitor_density"] == "low_signal"

    # Now six people actually APPLY (all strong).
    for sc in [90, 88, 82, 76, 71, 68]:
        _applicant(db_session, job_id=job.id, org_id=job.org_id, fit_score=sc)
    await db_session.flush()

    out2 = await competition_service.student_competition_intelligence(
        db_session, principal=student, job_id=job.id, student_fit_score=95,
    )
    assert out2["applicant_quality_bucket"] == "strong"
    assert out2["strong_competitor_density"] != "low_signal"
    assert out2["standing_vs_strong"] == "ahead"


async def test_quality_adjustment_beats_raw_volume(db_session) -> None:
    _u, student = await make_student(db_session)

    # Job 1: 32 applicants but only 2 strong, 5 seats.
    job1 = _make_visible_job(db_session, headcount=5)
    await db_session.flush()
    for i in range(30):
        _applicant(db_session, job_id=job1.id, org_id=job1.org_id, fit_score=20 + (i % 25))
    for sc in [90, 92]:
        _applicant(db_session, job_id=job1.id, org_id=job1.org_id, fit_score=sc)

    # Job 2: 20 applicants, ALL strong, 1 seat.
    job2 = _make_visible_job(db_session, headcount=1)
    await db_session.flush()
    for _ in range(20):
        _applicant(db_session, job_id=job2.id, org_id=job2.org_id, fit_score=90)
    await db_session.flush()

    out1 = await competition_service.student_competition_intelligence(
        db_session, principal=student, job_id=job1.id, student_fit_score=60,
    )
    out2 = await competition_service.student_competition_intelligence(
        db_session, principal=student, job_id=job2.id, student_fit_score=60,
    )

    # Job 1 has MORE total applicants but reads LOWER — caliber, not volume.
    assert out1["score"] < out2["score"]
    assert out1["label"] == "low"
    assert out2["label"] in ("high", "very_high")
    assert out1["strong_competitor_density"] == "few"
    assert out2["strong_competitor_density"] == "many"
    assert out1["basis"] == "applicant_caliber"


async def test_null_fit_applicants_are_unknown_not_zero(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session, headcount=1)
    await db_session.flush()

    # 5 uploaded-document applies (no fit) + 5 strong scored applies.
    for _ in range(5):
        _applicant(db_session, job_id=job.id, org_id=job.org_id, fit_score=None)
    for sc in [90, 88, 85, 82, 80]:
        _applicant(db_session, job_id=job.id, org_id=job.org_id, fit_score=sc)
    await db_session.flush()

    out = await competition_service.student_competition_intelligence(
        db_session, principal=student, job_id=job.id, student_fit_score=95,
    )
    # If NULL-fit applicants were counted as fit 0 the median would collapse to
    # developing; excluding them keeps the caliber pool honestly "strong".
    assert out["applicant_quality_bucket"] == "strong"


async def test_low_signal_below_min_pool(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session, headcount=1)
    await db_session.flush()

    # Only 2 active applicants -> below the low-signal application threshold.
    for sc in [80, 75]:
        _applicant(db_session, job_id=job.id, org_id=job.org_id, fit_score=sc)
    await db_session.flush()

    out = await competition_service.student_competition_intelligence(
        db_session, principal=student, job_id=job.id, student_fit_score=90,
    )
    assert out["signal"] == "low_signal"
    assert out["score"] is None
    assert out["label"] is None
    assert out["basis"] is None
    assert out["applicant_quality_bucket"] == "unknown"
    assert out["strong_competitor_density"] == "low_signal"


async def test_caliber_bands_guarded_when_few_scored(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session, headcount=1)
    await db_session.flush()

    # 6 active applicants (signal ok) but only 3 have a fit -> caliber unknown,
    # while the volume-based per-seat band is still emitted.
    for sc in [90, 85, 80]:
        _applicant(db_session, job_id=job.id, org_id=job.org_id, fit_score=sc)
    for _ in range(3):
        _applicant(db_session, job_id=job.id, org_id=job.org_id, fit_score=None)
    await db_session.flush()

    out = await competition_service.student_competition_intelligence(
        db_session, principal=student, job_id=job.id, student_fit_score=90,
    )
    assert out["signal"] == "ok"
    assert out["applicant_quality_bucket"] == "unknown"
    assert out["strong_competitor_density"] == "low_signal"
    assert out["standing_vs_strong"] == "low_signal"
    assert out["applicants_per_seat_band"] != "low_signal"


async def test_no_raw_counts_or_pii_in_payload(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session, headcount=2)
    await db_session.flush()
    ids: list[uuid.UUID] = []
    for sc in [90, 88, 82, 76, 71, 40, 35, 30]:
        aid = uuid.uuid4()
        ids.append(aid)
        snap_id = uuid.uuid4()
        db_session.add(
            ApplicationCvSnapshot(id=snap_id, user_id=aid, snapshot_json={}, fit_score=sc)
        )
        from app.modules.recruitment.domain.models import Application

        db_session.add(
            Application(
                id=uuid.uuid4(), job_id=job.id, applicant_id=aid,
                org_id=job.org_id, status="submitted", snapshot_id=snap_id,
            )
        )
    await db_session.flush()

    out = await competition_service.student_competition_intelligence(
        db_session, principal=student, job_id=job.id, student_fit_score=80,
    )
    blob = json.dumps(out, ensure_ascii=False)
    for aid in ids:
        assert str(aid) not in blob
    lowered = blob.lower()
    for term in (
        "percentile", "rank", "cv_id", "user_id", "applicant_id",
        "active_applications", "scored_applicants", "dist_strong", "dist_top",
    ):
        assert term not in lowered


# --------------------------------------------------------------------------- #
# Projection parity: projection-served bands == live-computed bands           #
# --------------------------------------------------------------------------- #

_BAND_KEYS = (
    "score", "label", "basis", "seats_bucket", "application_volume_bucket",
    "applicants_per_seat_band", "strong_competitor_density",
    "applicant_quality_bucket", "student_standing_bucket", "standing_vs_strong",
)


async def test_projection_refresh_matches_live_compute(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session, headcount=3)
    await db_session.flush()
    for sc in [90, 82, 75, 60, 55, 45, 40, 30]:
        _applicant(db_session, job_id=job.id, org_id=job.org_id, fit_score=sc)
    await db_session.flush()

    # First read: projection MISS -> live compute.
    live = await competition_service.student_competition_intelligence(
        db_session, principal=student, job_id=job.id, student_fit_score=70,
    )

    # Materialize the projection, then read again -> projection HIT.
    await competition_projection_service.refresh_job_competition(
        db_session, job_id=job.id, org_id=job.org_id, seats=job.headcount,
    )
    await db_session.flush()
    projected = await competition_service.student_competition_intelligence(
        db_session, principal=student, job_id=job.id, student_fit_score=70,
    )

    # The projection row exists and drives identical bands.
    row = await competition_projection_service._get_row(db_session, job_id=job.id)
    assert row is not None
    assert row.active_applications == 8
    # Strong contingent = fit >= 70: 90 (top), 82 + 75 (strong) -> 3.
    assert row.dist_strong + row.dist_top == 3
    for key in _BAND_KEYS:
        assert live[key] == projected[key], f"band drift on {key!r}"


# --------------------------------------------------------------------------- #
# AI narrative: on-demand + metered (deterministic bands stay free)           #
# --------------------------------------------------------------------------- #


async def _user_units(db_session, user_id) -> int:
    total = (
        await db_session.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.actor_user_id == user_id
            )
        )
    ).scalar_one()
    return int(total or 0)


def test_competition_explanation_feature_is_metered() -> None:
    # The narrative feature carries a small, cost-weighted energy price.
    assert energy_service.charge_units("competition_explanation") == 2


async def test_deterministic_bands_are_free(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session, headcount=1)
    await db_session.flush()
    for sc in [90, 85, 80, 75, 70]:
        _applicant(db_session, job_id=job.id, org_id=job.org_id, fit_score=sc)
    await db_session.flush()

    await competition_service.student_competition_intelligence(
        db_session, principal=student, job_id=job.id, student_fit_score=95,
    )
    # The bands read never touches the AI ledger.
    assert await _user_units(db_session, student.user_id) == 0


async def test_ai_narrative_offline_degrades_and_charges_nothing(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session, headcount=1)
    await db_session.flush()
    for sc in [90, 85, 80, 75, 70]:
        _applicant(db_session, job_id=job.id, org_id=job.org_id, fit_score=sc)
    await db_session.flush()

    out = await competition_service.competition_explanation(
        db_session, principal=student, job_id=job.id,
    )
    # Deterministic level present; the model is NOT invoked under the offline
    # provider, so no narrative and no charge.
    assert out["level"] in {"low", "medium", "high", "very_high"}
    assert out["explanation"] is None
    assert out["ai_explanation_available"] is False
    assert await _user_units(db_session, student.user_id) == 0


async def test_competition_energy_charge_is_idempotent(db_session) -> None:
    _u, student = await make_student(db_session)
    job = _make_visible_job(db_session, headcount=1)
    await db_session.flush()

    await competition_service._charge_competition_energy(
        db_session, principal=student, job_id=job.id, level="high",
    )
    await competition_service._charge_competition_energy(
        db_session, principal=student, job_id=job.id, level="high",
    )
    # Two charges for the same (job, level) -> billed once.
    assert await _user_units(db_session, student.user_id) == 2

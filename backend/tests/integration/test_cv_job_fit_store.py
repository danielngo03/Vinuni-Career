"""Persisted, version-stamped CV-JD fit-score store (Phase C).

Covers the store guarantees layered on top of the deterministic scorer:

- The deterministic score is identical across two calls (store round-trips it).
- A stored row is written after the first detail call.
- With UNCHANGED cv/job versions, the second detail call REUSES the stored
  explanation and does NOT re-invoke the LLM (call count stays at 1).
- Bumping ``job.version`` makes the next call recompute and regenerate the
  explanation (call count increments).
- Offline provider (AI gate off): explanation is null, the score is still
  present, and nothing crashes.
"""

from __future__ import annotations

import uuid

from app.ai.cv import job_fit, semantic_scorer
from app.modules.documents.application import job_fit_batch_service, job_fit_service
from app.modules.documents.domain.models import CvJobFitScore, CvProfile
from app.modules.opportunities.domain.models import Job
from sqlalchemy import select

from tests.documents_utils import make_student
from tests.integration.test_cv_job_fit import _build_strong_cv, _create_job


async def _fit_rows(db, *, user_id: uuid.UUID) -> list[CvJobFitScore]:
    return list(
        (
            await db.execute(
                select(CvJobFitScore).where(CvJobFitScore.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )


class _FakeSemantic:
    """Counting stand-in for ``semantic_scorer.analyze``.

    Records how many times the LLM path was invoked and returns a fixed summary
    so the store can persist an explanation on the recommended CV.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def analyze(
        self,
        *,
        job: dict,
        cv_text: str,
        cv_language: str,
        deterministic_score: int,
        matched_skills: list[str],
        gaps: list[str],
    ) -> semantic_scorer.SemanticFitResult:
        self.calls += 1
        return semantic_scorer.SemanticFitResult(
            score=deterministic_score,
            summary="This CV is a strong match for the role.",
        )


def _enable_ai(monkeypatch, fake: _FakeSemantic) -> None:
    """Turn both AI gates on and route ``analyze`` to the counting fake."""
    monkeypatch.setattr(job_fit_service, "real_provider_active", lambda: True)

    class _Cfg:
        job_fit_ai_explanation_enabled = True

    monkeypatch.setattr(
        job_fit_service.runtime_config, "current", lambda: _Cfg()
    )
    monkeypatch.setattr(semantic_scorer, "analyze", fake.analyze)
    # These tests exercise the store / explanation cache, not cross-lingual
    # translation-normalization; keep that tier off so scores stay lexical-only
    # + stable (the ``_Cfg`` above has no ``real_calls_active`` attribute).
    from app.ai.cv import skill_translation

    monkeypatch.setattr(skill_translation, "real_provider_active", lambda: False)


# --------------------------------------------------------------------------- #
# Deterministic score is identical + row is persisted                          #
# --------------------------------------------------------------------------- #


async def test_deterministic_score_identical_and_row_persisted(db_session) -> None:
    user, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    first = await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id
    )
    # Row written after the first call.
    rows = await _fit_rows(db_session, user_id=user.id)
    assert len(rows) == 1
    stored = rows[0]
    assert str(stored.cv_id) == cv_id
    assert str(stored.job_id) == str(job_id)
    assert stored.scorer_version == job_fit.SCORER_VERSION
    assert stored.score == first["results"][0]["score"]

    second = await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id
    )
    assert [r["score"] for r in first["results"]] == [
        r["score"] for r in second["results"]
    ]
    assert first["results"][0]["bands"] == second["results"][0]["bands"]
    assert first["recommended_cv_id"] == second["recommended_cv_id"]
    # Still exactly one row per (cv, job) — the second call updated, not inserted.
    assert len(await _fit_rows(db_session, user_id=user.id)) == 1


# --------------------------------------------------------------------------- #
# Unchanged versions -> explanation reused, LLM NOT re-invoked                 #
# --------------------------------------------------------------------------- #


async def test_explanation_reused_when_versions_unchanged(
    db_session, monkeypatch
) -> None:
    user, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    fake = _FakeSemantic()
    _enable_ai(monkeypatch, fake)

    first = await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id, with_explanation=True
    )
    assert first["ai_explanation_available"] is True
    rec = next(r for r in first["results"] if r["cv_id"] == first["recommended_cv_id"])
    assert rec["explanation"] == "This CV is a strong match for the role."
    assert fake.calls == 1

    # Second load, nothing changed -> explanation reused from the store, no LLM.
    second = await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id, with_explanation=True
    )
    assert second["ai_explanation_available"] is True
    rec2 = next(
        r for r in second["results"] if r["cv_id"] == second["recommended_cv_id"]
    )
    assert rec2["explanation"] == "This CV is a strong match for the role."
    assert fake.calls == 1  # NOT re-invoked

    # Explanation stamped on the stored row.
    rows = await _fit_rows(db_session, user_id=user.id)
    stored = next(r for r in rows if str(r.cv_id) == cv_id)
    assert stored.explanation == "This CV is a strong match for the role."
    assert stored.explanation_prompt_version == semantic_scorer.PROMPT_VERSION


# --------------------------------------------------------------------------- #
# Bumping job.version -> recompute + regenerate explanation                    #
# --------------------------------------------------------------------------- #


async def test_job_version_bump_regenerates_explanation(
    db_session, monkeypatch
) -> None:
    _user, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    fake = _FakeSemantic()
    _enable_ai(monkeypatch, fake)

    await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id, with_explanation=True
    )
    assert fake.calls == 1

    # Employer edits the JD -> job.version bumps -> the stored row is stale.
    job = (
        await db_session.execute(select(Job).where(Job.id == job_id))
    ).scalar_one()
    job.version = job.version + 1
    await db_session.commit()

    out = await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id, with_explanation=True
    )
    assert out["ai_explanation_available"] is True
    assert fake.calls == 2  # regenerated because the content version moved


# --------------------------------------------------------------------------- #
# Bumping cv.version -> recompute + regenerate explanation                     #
# --------------------------------------------------------------------------- #


async def test_cv_version_bump_regenerates_explanation(
    db_session, monkeypatch
) -> None:
    _user, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    fake = _FakeSemantic()
    _enable_ai(monkeypatch, fake)

    await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id, with_explanation=True
    )
    assert fake.calls == 1

    # Student edits the CV so its content changes: seed a different skills set so
    # the deterministic matched skills + gaps (and thus the reuse fingerprint)
    # actually move, then bump cv.version. New evidence -> no cross-CV reuse hit
    # -> the explanation regenerates.
    from tests.integration.test_cv_job_fit import _seed

    await _seed(
        db_session, cv_id, "skills", [{"text": "Java, Spring Boot, Kotlin"}]
    )
    cv = (
        await db_session.execute(
            select(CvProfile).where(CvProfile.id == uuid.UUID(cv_id))
        )
    ).scalar_one()
    cv.version = cv.version + 1
    await db_session.commit()

    await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id, with_explanation=True
    )
    assert fake.calls == 2


# --------------------------------------------------------------------------- #
# Batch (list) path is store-backed and deterministic-only                     #
# --------------------------------------------------------------------------- #


class _FakeRedis:
    """Minimal in-memory Redis for the batch cache (get/setex only)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self._data[key] = value


async def test_batch_path_writes_rows_and_reuses_store(db_session) -> None:
    user, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)
    redis = _FakeRedis()

    first = await job_fit_batch_service.batch_fit_for_jobs(
        db_session, redis, principal=student, job_ids=[job_id]
    )
    entry = first[str(job_id)]
    assert set(entry) == {"score", "recommended_cv_id", "signal", "stale"}
    assert entry["recommended_cv_id"] == cv_id
    assert entry["score"] > 0

    # A fit row was persisted by the batch (deterministic-only) path.
    rows = await _fit_rows(db_session, user_id=user.id)
    assert len(rows) == 1
    assert rows[0].explanation is None  # batch path never calls the LLM

    # Fresh Redis (cache bypassed) -> served from the store, no new rows.
    second = await job_fit_batch_service.batch_fit_for_jobs(
        db_session, _FakeRedis(), principal=student, job_ids=[job_id]
    )
    assert second[str(job_id)]["score"] == entry["score"]
    assert len(await _fit_rows(db_session, user_id=user.id)) == 1


# --------------------------------------------------------------------------- #
# Offline provider (AI gate off): explanation null, score present, no crash    #
# --------------------------------------------------------------------------- #


async def test_offline_provider_null_explanation_score_present(db_session) -> None:
    _user, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    out = await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id
    )
    assert out["ai_explanation_available"] is False
    assert all(r["explanation"] is None for r in out["results"])
    assert out["results"][0]["score"] > 0


# --------------------------------------------------------------------------- #
# SCORER_VERSION bump invalidates stored rows                                  #
# --------------------------------------------------------------------------- #


async def test_scorer_version_bump_recomputes(db_session, monkeypatch) -> None:
    _user, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    fake = _FakeSemantic()
    _enable_ai(monkeypatch, fake)

    first = await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id, with_explanation=True
    )
    assert fake.calls == 1

    # A scorer change (weights/logic/ontology) bumps SCORER_VERSION -> the stored
    # rows are stale and the DETERMINISTIC score is recomputed.
    monkeypatch.setattr(job_fit, "SCORER_VERSION", job_fit.SCORER_VERSION + "-next")

    second = await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id, with_explanation=True
    )
    # The CV content (and thus matched skills + gaps) is unchanged, so the reuse
    # fingerprint is identical: the cross-CV "learning" cache serves the same
    # requirement-centric explanation WITHOUT a new LLM call. The explanation is
    # not tied to SCORER_VERSION (the number, not the "why", moved).
    assert fake.calls == 1
    assert second["ai_explanation_available"] is True
    rec = next(
        r for r in second["results"] if r["cv_id"] == second["recommended_cv_id"]
    )
    assert rec["explanation"] == first["results"][0]["explanation"]

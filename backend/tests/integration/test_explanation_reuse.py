"""Cross-CV fit-explanation reuse cache (the "learning" cache).

At scale many DIFFERENT students apply to the SAME popular JD. Two CVs that
produce the SAME deterministic evidence (matched skills + gaps) against the SAME
JD version share ONE generated explanation — the second CV reuses the first CV's
requirement-centric summary at 0 extra tokens instead of triggering its own LLM
call.

These tests run fully offline: the LLM (``semantic_scorer.analyze``) is
monkeypatched with a call counter, and both AI gates are forced on. They assert:

- Two DIFFERENT CVs (different cv_id) crafted to produce the SAME deterministic
  matched skills + gaps against the SAME job REUSE one generation: the first
  detail load generates (count == 1); a load recommending the OTHER CV reuses
  it (count stays 1). Both get a non-null explanation.
- A DIFFERENT job (different fingerprint) generates separately (count
  increments).
- Bumping the job version yields a new fingerprint -> regenerates.
- AI gate off -> no explanation, no crash, no cache write.
"""

from __future__ import annotations

import uuid

from app.ai.cv import semantic_scorer
from app.modules.documents.application import fit_store, job_fit_service
from app.modules.documents.domain.models import (
    CvFitExplanationCache,
    CvJobFitScore,
)
from app.modules.opportunities.domain.models import Job
from sqlalchemy import select

from tests.documents_utils import make_student
from tests.integration.test_cv_job_fit import _build_strong_cv, _create_job


class _CountingSemantic:
    """Counting stand-in for ``semantic_scorer.analyze`` (a requirement-centric,
    CV-agnostic summary)."""

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
            summary="Meets the core Python/FastAPI requirements for this role.",
        )


def _enable_ai(monkeypatch, fake: _CountingSemantic) -> None:
    """Force both AI gates on and route ``analyze`` to the counting fake."""
    monkeypatch.setattr(job_fit_service, "real_provider_active", lambda: True)

    class _Cfg:
        job_fit_ai_explanation_enabled = True

    monkeypatch.setattr(job_fit_service.runtime_config, "current", lambda: _Cfg())
    monkeypatch.setattr(semantic_scorer, "analyze", fake.analyze)
    # These tests exercise explanation caching, not cross-lingual
    # translation-normalization; keep that tier off so the deterministic
    # score/matched/gaps stay lexical-only (the ``_Cfg`` above has no
    # ``real_calls_active`` attribute).
    from app.ai.cv import skill_translation

    monkeypatch.setattr(skill_translation, "real_provider_active", lambda: False)


async def _cache_rows(db) -> list[CvFitExplanationCache]:
    return list((await db.execute(select(CvFitExplanationCache))).scalars().all())


async def _recommended_explanation(out: dict) -> str | None:
    rec = next(r for r in out["results"] if r["cv_id"] == out["recommended_cv_id"])
    return rec["explanation"]


# --------------------------------------------------------------------------- #
# Two different CVs, same evidence, same job -> ONE generation (cross-CV reuse) #
# --------------------------------------------------------------------------- #


async def test_two_cvs_same_evidence_reuse_one_generation(db_session, monkeypatch) -> None:
    _user, student_a = await make_student(db_session)
    _user_b, student_b = await make_student(db_session)

    # Two DIFFERENT CVs (different owners/cv_ids) with IDENTICAL section content
    # -> identical deterministic matched skills + gaps -> same fingerprint.
    cv_a = await _build_strong_cv(db_session, student_a, title="CV A")
    cv_b = await _build_strong_cv(db_session, student_b, title="CV B")
    assert cv_a != cv_b
    job_id = await _create_job(db_session)

    fake = _CountingSemantic()
    _enable_ai(monkeypatch, fake)

    # Student A loads the job detail first -> LLM generates once.
    out_a = await job_fit_service.job_fit_for_job(
        db_session, principal=student_a, job_id=job_id, with_explanation=True
    )
    assert out_a["ai_explanation_available"] is True
    assert await _recommended_explanation(out_a) is not None
    assert fake.calls == 1

    # A row seeded the cross-CV cache exactly once.
    cache = await _cache_rows(db_session)
    assert len(cache) == 1

    # Student B loads the SAME job with the OTHER CV -> equivalent evidence ->
    # REUSE the cached explanation, LLM NOT re-invoked.
    out_b = await job_fit_service.job_fit_for_job(
        db_session, principal=student_b, job_id=job_id, with_explanation=True
    )
    assert out_b["ai_explanation_available"] is True
    assert await _recommended_explanation(out_b) is not None
    assert fake.calls == 1  # cross-CV reuse: no second generation

    # Still one cache entry; its hit_count incremented on reuse.
    cache = await _cache_rows(db_session)
    assert len(cache) == 1
    assert cache[0].hit_count == 1

    # Both CVs now carry the explanation on their own fit row.
    rows = (await db_session.execute(select(CvJobFitScore))).scalars().all()
    explained = [r for r in rows if r.explanation is not None]
    assert {str(r.cv_id) for r in explained} == {cv_a, cv_b}


# --------------------------------------------------------------------------- #
# Fingerprint helper: same evidence -> same fp; order-insensitive              #
# --------------------------------------------------------------------------- #


def test_fingerprint_is_order_insensitive_and_content_sensitive() -> None:
    job_id = uuid.uuid4()
    fp1 = fit_store.explanation_fingerprint(
        job_id=job_id,
        job_version=1,
        matched_skills=["Python", "FastAPI"],
        gaps=["Docker"],
        prompt_version=3,
        lang="en",
    )
    # Reordered lists -> identical fingerprint (both sorted internally).
    fp2 = fit_store.explanation_fingerprint(
        job_id=job_id,
        job_version=1,
        matched_skills=["FastAPI", "Python"],
        gaps=["Docker"],
        prompt_version=3,
        lang="en",
    )
    assert fp1 == fp2

    # Different evidence -> different fingerprint.
    fp3 = fit_store.explanation_fingerprint(
        job_id=job_id,
        job_version=1,
        matched_skills=["Python"],
        gaps=["Docker", "Kubernetes"],
        prompt_version=3,
        lang="en",
    )
    assert fp3 != fp1

    # Bumping the job version -> different fingerprint.
    fp4 = fit_store.explanation_fingerprint(
        job_id=job_id,
        job_version=2,
        matched_skills=["Python", "FastAPI"],
        gaps=["Docker"],
        prompt_version=3,
        lang="en",
    )
    assert fp4 != fp1


# --------------------------------------------------------------------------- #
# Different job -> different fingerprint -> separate generation                #
# --------------------------------------------------------------------------- #


async def test_different_job_generates_separately(db_session, monkeypatch) -> None:
    _user, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_a = await _create_job(db_session)
    # A different job with DIFFERENT required skills -> different matched/gaps ->
    # a different fingerprint.
    job_b = await _create_job(
        db_session,
        title="Data Analyst",
        required_skills=["SQL", "Excel", "Tableau"],
        preferred_skills=["Power BI"],
    )

    fake = _CountingSemantic()
    _enable_ai(monkeypatch, fake)

    await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_a, with_explanation=True
    )
    assert fake.calls == 1

    await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_b, with_explanation=True
    )
    assert fake.calls == 2  # distinct evidence -> distinct fingerprint -> generate

    assert len(await _cache_rows(db_session)) == 2


# --------------------------------------------------------------------------- #
# Bumping job.version -> new fingerprint -> regenerate                         #
# --------------------------------------------------------------------------- #


async def test_job_version_bump_new_fingerprint_regenerates(db_session, monkeypatch) -> None:
    _user, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    fake = _CountingSemantic()
    _enable_ai(monkeypatch, fake)

    await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id, with_explanation=True
    )
    assert fake.calls == 1
    assert len(await _cache_rows(db_session)) == 1

    # Employer edits the JD -> job.version bumps -> the row is stale AND the
    # fingerprint changes -> a fresh generation (no cross-CV reuse).
    job = (await db_session.execute(select(Job).where(Job.id == job_id))).scalar_one()
    job.version = job.version + 1
    await db_session.commit()

    await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id, with_explanation=True
    )
    assert fake.calls == 2
    assert len(await _cache_rows(db_session)) == 2  # new fingerprint -> new entry


# --------------------------------------------------------------------------- #
# AI gate off -> no explanation, no crash, no cache write                      #
# --------------------------------------------------------------------------- #


async def test_ai_gate_off_no_explanation_no_cache(db_session) -> None:
    _user, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    # Default offline provider (no gate patching) -> both AI gates closed.
    out = await job_fit_service.job_fit_for_job(db_session, principal=student, job_id=job_id)
    assert out["ai_explanation_available"] is False
    assert all(r["explanation"] is None for r in out["results"])
    assert out["results"][0]["score"] > 0
    assert await _cache_rows(db_session) == []

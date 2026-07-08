"""Fast-score / async-explanation split for student job intelligence.

The job-detail intelligence panel used to stall 20-30s because
``student_intelligence_for_job`` -> ``job_fit_service.job_fit_for_job`` computed
the LLM ``explanation`` synchronously before returning. The score/bands are
deterministic and fast; only the explanation is slow. This slice splits them:

- ``student_intelligence_for_job`` (and ``job_fit_for_job`` by default) now run
  ``with_explanation=False`` -> deterministic-only, the LLM is NEVER invoked, so
  the endpoint returns immediately with ``fit.explanation is None``.
- The AI narrative is loaded separately via ``fit_explanation_for_job``
  (``GET /jobs/{job_id}/fit-explanation``), which reuses the exact same shared
  explanation block as the legacy inline path.

These tests run fully offline: ``semantic_scorer.analyze`` is monkeypatched with
a call counter and both AI gates are forced on/off explicitly.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.cv import semantic_scorer, skill_translation
from app.main import app
from app.modules.documents.application import job_fit_service
from app.modules.opportunities.application import student_intelligence_service
from httpx import ASGITransport, AsyncClient

from tests.documents_utils import make_student
from tests.integration.test_cv_job_fit import _build_strong_cv, _create_job


class _CountingSemantic:
    """Counting stand-in for ``semantic_scorer.analyze`` (CV-agnostic summary)."""

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
    # Keep the cross-lingual translation tier OFF so the deterministic
    # matched/gaps stay lexical-only (matches test_explanation_reuse).
    monkeypatch.setattr(skill_translation, "real_provider_active", lambda: False)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


# --------------------------------------------------------------------------- #
# 1. Student-intelligence returns FAST and never invokes the LLM               #
# --------------------------------------------------------------------------- #


async def test_student_intelligence_is_fast_and_never_calls_llm(
    db_session, monkeypatch
) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    # AI gates ON + counting analyze: if the student-intelligence path touched
    # the LLM at all, ``fake.calls`` would increment. It must stay 0.
    fake = _CountingSemantic()
    _enable_ai(monkeypatch, fake)

    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None,
    )

    assert out["fit"]["status"] == "scored"
    assert out["fit"]["score"] is not None
    assert out["fit"]["bands"] is not None
    # Deterministic-only: NO explanation on the fast path.
    assert out["fit"].get("explanation") is None
    # The LLM was never invoked in the student-intelligence path.
    assert fake.calls == 0


async def test_job_fit_default_skips_explanation(db_session, monkeypatch) -> None:
    """``job_fit_for_job`` default (``with_explanation=False``) never calls the LLM."""
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    fake = _CountingSemantic()
    _enable_ai(monkeypatch, fake)

    out = await job_fit_service.job_fit_for_job(
        db_session, principal=student, job_id=job_id
    )
    assert out["ai_explanation_available"] is False
    assert all(r["explanation"] is None for r in out["results"])
    assert out["results"][0]["score"] > 0
    assert fake.calls == 0


# --------------------------------------------------------------------------- #
# 2. fit_explanation_for_job                                                    #
# --------------------------------------------------------------------------- #


async def test_fit_explanation_recommended_cv_with_ai_on(
    db_session, monkeypatch
) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    fake = _CountingSemantic()
    _enable_ai(monkeypatch, fake)

    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None,
    )
    assert out["cv_id"] == cv_id
    assert out["explanation"] is not None
    assert out["ai_explanation_available"] is True
    assert fake.calls == 1


async def test_fit_explanation_specific_valid_cv(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    # Two library CVs; explicitly ask for the weaker one by id.
    strong = await _build_strong_cv(db_session, student, title="Strong CV")
    weak_cv = await _build_strong_cv(db_session, student, title="Weak CV")
    assert strong != weak_cv
    job_id = await _create_job(db_session)

    fake = _CountingSemantic()
    _enable_ai(monkeypatch, fake)

    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id, cv_id=uuid.UUID(weak_cv),
    )
    assert out["cv_id"] == weak_cv
    assert out["explanation"] is not None
    assert out["ai_explanation_available"] is True


async def test_fit_explanation_foreign_cv_falls_back_to_recommended(
    db_session, monkeypatch
) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    fake = _CountingSemantic()
    _enable_ai(monkeypatch, fake)

    # A cv_id the caller does not own -> fall back to the recommended CV (no 404).
    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id, cv_id=uuid.uuid4(),
    )
    assert out["cv_id"] == cv_id
    assert out["explanation"] is not None
    assert out["ai_explanation_available"] is True


async def test_fit_explanation_ai_off_returns_null_no_crash(db_session) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    # Default offline provider (no gate patching) -> both AI gates closed.
    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None,
    )
    assert out["explanation"] is None
    assert out["ai_explanation_available"] is False
    # cv_id still identifies the recommended CV (score is fast/deterministic).
    assert out["cv_id"] is not None


async def test_fit_explanation_no_active_cv_returns_null(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)

    fake = _CountingSemantic()
    _enable_ai(monkeypatch, fake)

    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id, cv_id=None,
    )
    assert out == {
        "cv_id": None,
        "explanation": None,
        "ai_explanation_available": False,
    }
    assert fake.calls == 0


async def test_fit_explanation_reuses_fresh_row_no_second_call(
    db_session, monkeypatch
) -> None:
    """A second explanation request reuses the stored row -> LLM not re-invoked."""
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)

    fake = _CountingSemantic()
    _enable_ai(monkeypatch, fake)

    first = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id,
    )
    assert first["explanation"] is not None
    assert fake.calls == 1

    second = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id,
    )
    assert second["explanation"] == first["explanation"]
    assert fake.calls == 1  # fresh-row reuse: no second generation


# --------------------------------------------------------------------------- #
# 3. Router auth guard                                                          #
# --------------------------------------------------------------------------- #


async def test_fit_explanation_route_requires_auth(client) -> None:
    resp = await client.get(f"/jobs/{uuid.uuid4()}/fit-explanation")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_fit_explanation_route_rejects_bogus_token(client) -> None:
    resp = await client.get(
        f"/jobs/{uuid.uuid4()}/fit-explanation",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401

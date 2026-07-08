"""CV-JD fit EXPLANATION debits the STUDENT's AI energy (deterministic score is free).

Service-layer charge on the freshly-generated narrative only: charged once per
(job, cv) content version; a reload reuses the cached explanation and never
re-charges; the AI gate being off (or the weekly energy being exhausted) degrades
to no-explanation and charges 0 — the deterministic score is unaffected either way.
"""

from __future__ import annotations

from app.ai.cv import semantic_scorer, skill_translation
from app.ai.energy.service import charge_units
from app.ai.observability.models import AiBillableUsage
from app.modules.documents.application import job_fit_service
from app.shared.exceptions import QuotaExceededError
from sqlalchemy import func, select
from tests.documents_utils import make_student
from tests.integration.test_cv_job_fit import _build_strong_cv, _create_job


class _FakeSemantic:
    """Stand-in for ``semantic_scorer.analyze`` (signature UNCHANGED by metering)."""

    def __init__(self) -> None:
        self.calls = 0

    async def analyze(
        self, *, job, cv_text, cv_language, deterministic_score, matched_skills, gaps
    ) -> semantic_scorer.SemanticFitResult:
        self.calls += 1
        return semantic_scorer.SemanticFitResult(
            score=deterministic_score,
            summary="Meets the core Python/FastAPI requirements for this role.",
        )


def _enable_ai(monkeypatch, fake: _FakeSemantic) -> None:
    monkeypatch.setattr(job_fit_service, "real_provider_active", lambda: True)

    class _Cfg:
        job_fit_ai_explanation_enabled = True

    monkeypatch.setattr(job_fit_service.runtime_config, "current", lambda: _Cfg())
    monkeypatch.setattr(semantic_scorer, "analyze", fake.analyze)
    monkeypatch.setattr(skill_translation, "real_provider_active", lambda: False)


async def _user_units(db, user_id) -> int:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.actor_user_id == user_id
            )
        )
    ).scalar_one()
    return int(total or 0)


async def _fit_row(db, user_id):
    return (
        await db.execute(
            select(AiBillableUsage).where(
                AiBillableUsage.actor_user_id == user_id,
                AiBillableUsage.feature_key == "cv_fit_explanation",
            )
        )
    ).scalars().all()


async def test_fit_explanation_success_charges_student(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)
    fake = _FakeSemantic()
    _enable_ai(monkeypatch, fake)

    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id
    )

    assert out["explanation"]
    assert out["ai_explanation_available"] is True
    assert fake.calls == 1
    assert await _user_units(db_session, student.user_id) == charge_units("cv_fit_explanation")
    rows = await _fit_row(db_session, student.user_id)
    assert len(rows) == 1
    assert rows[0].billing_scope == "user"
    assert rows[0].result_status == "success"


async def test_fit_explanation_reuse_does_not_double_charge(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)
    fake = _FakeSemantic()
    _enable_ai(monkeypatch, fake)

    await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id
    )
    # Same content version -> cached explanation, NO second model call, NO charge.
    await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id
    )

    assert fake.calls == 1
    assert await _user_units(db_session, student.user_id) == charge_units("cv_fit_explanation")


async def test_fit_explanation_ai_gate_off_charges_zero(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)
    # AI gate OFF (default offline): deterministic score returns, explanation null.
    monkeypatch.setattr(job_fit_service, "real_provider_active", lambda: False)

    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id
    )

    assert out["explanation"] is None
    assert await _user_units(db_session, student.user_id) == 0


async def test_fit_explanation_energy_exhausted_degrades_no_charge(
    db_session, monkeypatch
) -> None:
    _u, student = await make_student(db_session)
    await _build_strong_cv(db_session, student)
    job_id = await _create_job(db_session)
    fake = _FakeSemantic()
    _enable_ai(monkeypatch, fake)

    async def _blocked(session, *, principal):
        raise QuotaExceededError("out of energy")

    monkeypatch.setattr(job_fit_service.energy_service, "enforce_energy", _blocked)

    out = await job_fit_service.fit_explanation_for_job(
        db_session, principal=student, job_id=job_id
    )

    # Exhaustion degrades the ADVISORY narrative to null (no 409 on this read) and
    # never spends the model — the deterministic score is unaffected upstream.
    assert out["explanation"] is None
    assert fake.calls == 0
    assert await _user_units(db_session, student.user_id) == 0

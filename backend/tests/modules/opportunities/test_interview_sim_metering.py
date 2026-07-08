"""Interview simulator (prep + answer feedback) debits the STUDENT's AI energy.

The offline provider returns plain text, so the JSON-note path parses to
``validation_failed`` unless the runner is fed valid JSON — mirroring
``test_energy_metering``, the success cases monkeypatch ``AiTaskRunner.complete``
with a valid JSON completion. A provider failure charges 0 and degrades to the
static question bank / static feedback.
"""

from __future__ import annotations

import json

from app.ai.energy.service import charge_units
from app.ai.gateway import task_runner as tr
from app.ai.gateway.base import AICompletion
from app.ai.observability.models import AiBillableUsage
from app.modules.opportunities.application import interview_sim_service
from app.shared.exceptions import AIUnavailableError
from sqlalchemy import func, select
from tests.documents_utils import make_student
from tests.integration.test_cv_job_fit import _create_job

_PREP_JSON = {
    "questions": [
        {"type": "behavioral", "question": "Tell me about a project.",
         "hint": "STAR", "rubric": "structured"},
    ],
    "prep_tips": "Prepare STAR stories.",
}
_FEEDBACK_JSON = {
    "score": 4,
    "praise": "Clear structure.",
    "improve": "Add a measurable outcome.",
    "hint": "Quantify impact.",
}


async def _user_units(db, user_id) -> int:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.actor_user_id == user_id
            )
        )
    ).scalar_one()
    return int(total or 0)


async def _status_for(db, user_id) -> str | None:
    return (
        await db.execute(
            select(AiBillableUsage.result_status).where(
                AiBillableUsage.actor_user_id == user_id
            )
        )
    ).scalar_one_or_none()


def _patch_json(monkeypatch, payload: dict) -> None:
    async def _complete(self, messages, *, temperature=0.2, max_tokens=1024):
        return AICompletion(text=json.dumps(payload), model_alias="x")

    monkeypatch.setattr(tr.AiTaskRunner, "complete", _complete)


async def test_interview_prep_success_charges_student(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)
    _patch_json(monkeypatch, _PREP_JSON)

    out = await interview_sim_service.generate_interview_prep(
        db_session, principal=student, job_id=job_id
    )

    assert out["is_fallback"] is False
    assert await _user_units(db_session, student.user_id) == charge_units("interview_sim")
    assert await _status_for(db_session, student.user_id) == "success"


async def test_answer_feedback_success_charges_student(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)
    _patch_json(monkeypatch, _FEEDBACK_JSON)

    out = await interview_sim_service.evaluate_answer(
        db_session, principal=student, job_id=job_id,
        question="Tell me about a project.", question_type="behavioral",
        rubric="structured", answer="I built a REST API.",
    )

    assert out["is_fallback"] is False
    assert await _user_units(db_session, student.user_id) == charge_units("interview_sim")


async def test_interview_prep_provider_failure_charges_zero(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)

    async def _boom(self, messages, *, temperature=0.2, max_tokens=1024):
        raise AIUnavailableError()

    monkeypatch.setattr(tr.AiTaskRunner, "complete", _boom)

    out = await interview_sim_service.generate_interview_prep(
        db_session, principal=student, job_id=job_id
    )

    assert out["is_fallback"] is True  # static question bank
    assert await _user_units(db_session, student.user_id) == 0

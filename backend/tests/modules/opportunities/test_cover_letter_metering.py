"""Cover-letter draft debits the STUDENT's AI energy (offline provider).

Mirrors ``test_jd_metering`` for the student side: a successful draft charges one
cover-letter credit to the student's user scope; a provider failure charges 0 and
degrades to the deterministic static draft. No provider/model/token leakage.
"""

from __future__ import annotations

from app.ai.energy.service import charge_units
from app.ai.gateway import task_runner as tr
from app.ai.observability.models import AiBillableUsage
from app.modules.opportunities.application import cover_letter_service
from app.shared.exceptions import AIUnavailableError
from sqlalchemy import func, select
from tests.documents_utils import make_student
from tests.integration.test_cv_job_fit import _create_job


async def _user_units(db, user_id) -> int:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.actor_user_id == user_id
            )
        )
    ).scalar_one()
    return int(total or 0)


async def _rows_for(db, user_id) -> list[AiBillableUsage]:
    return list(
        (
            await db.execute(
                select(AiBillableUsage).where(AiBillableUsage.actor_user_id == user_id)
            )
        )
        .scalars()
        .all()
    )


async def test_cover_letter_success_charges_student(db_session) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)

    out = await cover_letter_service.generate_cover_letter(
        db_session, principal=student, job_id=job_id
    )

    assert out["is_fallback"] is False
    assert out["draft"]
    # One cover-letter credit charged to the student's own user scope.
    assert await _user_units(db_session, student.user_id) == charge_units("cover_letter")
    rows = await _rows_for(db_session, student.user_id)
    assert len(rows) == 1
    assert rows[0].feature_key == "cover_letter"
    assert rows[0].billing_scope == "user"
    assert rows[0].result_status == "success"
    # No provider/model/token leakage in the user-visible draft.
    blob = out["draft"].lower()
    for term in ("openrouter", "openai", "gpt-4", "gemini", "model_alias", "prompt_tokens"):
        assert term not in blob


async def test_cover_letter_provider_failure_charges_zero(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)

    async def _boom(self, messages, *, temperature=0.2, max_tokens=1024):
        raise AIUnavailableError()

    monkeypatch.setattr(tr.AiTaskRunner, "complete", _boom)

    out = await cover_letter_service.generate_cover_letter(
        db_session, principal=student, job_id=job_id
    )

    # Degrades to the deterministic static draft; nothing billed.
    assert out["is_fallback"] is True
    assert await _user_units(db_session, student.user_id) == 0
    rows = await _rows_for(db_session, student.user_id)
    assert all(r.result_status != "success" for r in rows)

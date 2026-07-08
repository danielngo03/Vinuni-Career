"""JD extraction + translation debit the partner org's AI energy.

Extraction is charged at the service layer from the cascade's tier diagnostics
(vision > text > native-only=free); translation is charged to the job's owning
org, idempotent per (job, lang).
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.extraction.jd.cascade import JdExtractionOutcome
from app.ai.observability.models import AiBillableUsage
from app.modules.opportunities.application import jd_upload_service, translation_service
from app.shared.permissions import Principal
from sqlalchemy import func, select


def _partner() -> Principal:
    return Principal(user_id=uuid.uuid4(), persona="partner_member", org_id=uuid.uuid4())


async def _org_units(db_session, org_id) -> int:
    total = (
        await db_session.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.org_id == org_id
            )
        )
    ).scalar_one()
    return int(total or 0)


async def _org_status(db_session, org_id) -> str | None:
    return (
        await db_session.execute(
            select(AiBillableUsage.result_status).where(
                AiBillableUsage.org_id == org_id
            )
        )
    ).scalar_one_or_none()


async def test_text_extraction_charges_org(db_session) -> None:
    p = _partner()
    outcome = JdExtractionOutcome(status="ok", is_ai_extraction=True, llm_used=True)
    await jd_upload_service._meter_extraction(db_session, p, outcome)
    from app.ai.energy.service import charge_units

    assert await _org_units(db_session, p.org_id) == charge_units("jd_extraction")
    assert await _org_status(db_session, p.org_id) == "success"


async def test_vision_extraction_charges_more(db_session) -> None:
    p = _partner()
    outcome = JdExtractionOutcome(
        status="ok", is_ai_extraction=True, vision_used=True, llm_used=False
    )
    await jd_upload_service._meter_extraction(db_session, p, outcome)
    from app.ai.energy.service import charge_units

    assert await _org_units(db_session, p.org_id) == charge_units("jd_vision_extraction")
    assert await _org_units(db_session, p.org_id) > charge_units("jd_extraction")


async def test_native_text_only_is_free(db_session) -> None:
    p = _partner()
    # No LLM/vision tier ran → zero tokens → nothing recorded.
    outcome = JdExtractionOutcome(
        status="ok", is_ai_extraction=False, llm_used=False, vision_used=False
    )
    await jd_upload_service._meter_extraction(db_session, p, outcome)
    count = (
        await db_session.execute(
            select(func.count()).select_from(AiBillableUsage).where(
                AiBillableUsage.org_id == p.org_id
            )
        )
    ).scalar_one()
    assert count == 0


async def test_ai_unavailable_records_zero(db_session) -> None:
    p = _partner()
    outcome = JdExtractionOutcome(status="ai_unavailable", is_ai_extraction=False)
    await jd_upload_service._meter_extraction(db_session, p, outcome)
    assert await _org_units(db_session, p.org_id) == 0
    assert await _org_status(db_session, p.org_id) == "provider_failed"


async def test_no_principal_no_charge(db_session) -> None:
    outcome = JdExtractionOutcome(status="ok", is_ai_extraction=True, llm_used=True)
    # db present but no principal → no attribution possible → no-op.
    await jd_upload_service._meter_extraction(db_session, None, outcome)
    count = (
        await db_session.execute(select(func.count()).select_from(AiBillableUsage))
    ).scalar_one()
    assert count == 0


# --------------------------------------------------------------------------- #
# Translation wiring: org_id + usage_context + charge_units reach the runner    #
# --------------------------------------------------------------------------- #


async def test_translation_passes_org_metering_to_runner(db_session, monkeypatch) -> None:
    from app.ai.gateway import task_runner as tr
    from app.ai.gateway.base import AICompletion

    captured: dict = {}
    orig_init = tr.AiTaskRunner.__init__

    def spy_init(self, db, **kw):
        captured.update(kw)
        orig_init(self, db, **kw)

    async def fake_complete(self, messages, *, temperature=0.2, max_tokens=1024):
        return AICompletion(
            text='{"title":"Kỹ sư","description":"...","requirements":null,"benefits":null}',
            model_alias="x",
            usage={},
            finish_reason="stop",
        )

    monkeypatch.setattr(tr.AiTaskRunner, "__init__", spy_init)
    monkeypatch.setattr(tr.AiTaskRunner, "complete", fake_complete)

    org_id = uuid.uuid4()

    class _JobStub:
        id = uuid.uuid4()
        language_code = "vi"
        title = "Kỹ sư phần mềm"
        description = "Mô tả công việc chi tiết ..."
        requirements = None
        benefits = None

    job = _JobStub()
    job.org_id = org_id  # type: ignore[attr-defined]

    from app.ai.energy.constants import FEATURE_JD_TRANSLATION
    from app.ai.energy.service import charge_units
    from app.ai.observability.billable_usage import (
        PERSONA_PARTNER,
        SCOPE_ORG,
        UsageContext,
    )

    ctx = UsageContext(
        actor_persona=PERSONA_PARTNER,
        feature_key=FEATURE_JD_TRANSLATION,
        task_type="jd_translation",
        billing_scope=SCOPE_ORG,
        org_id=org_id,
    )

    result = await translation_service._ai_translate(
        job,
        target_lang="en",
        session=db_session,
        org_id=org_id,
        usage_context=ctx,
        charge_units=charge_units(FEATURE_JD_TRANSLATION),
    )

    assert result is not None
    assert captured.get("org_id") == org_id
    assert captured.get("usage_context") is ctx
    assert captured.get("charge_units") == charge_units(FEATURE_JD_TRANSLATION)

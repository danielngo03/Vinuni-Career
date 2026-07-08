"""Metered-gateway routing + billable charging for the shared LLM helpers.

Verifies that ``app.ai.cv.llm.generate_note`` / ``generate_json_note`` — the
helpers every partner AI feature (JD extraction/writer, screening brief,
scorecard, market intel) routes through — now debit the partner org's energy
ledger on success, record 0 credits on provider/validation failure, and attribute
the ``ai_usage_log`` row to ``org_id``.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.cv import llm
from app.ai.energy import service as energy
from app.ai.gateway import task_runner as tr
from app.ai.gateway.base import AICompletion
from app.ai.observability.models import AiBillableUsage, AiUsageLog
from app.shared.exceptions import AIUnavailableError
from app.shared.permissions import Principal
from sqlalchemy import func, select


def _partner_principal() -> Principal:
    return Principal(
        user_id=uuid.uuid4(), persona="partner_member", org_id=uuid.uuid4()
    )


async def _org_units(db_session, org_id) -> int:
    total = (
        await db_session.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.org_id == org_id
            )
        )
    ).scalar_one()
    return int(total or 0)


async def _ledger_status(db_session, org_id) -> str | None:
    return (
        await db_session.execute(
            select(AiBillableUsage.result_status).where(
                AiBillableUsage.org_id == org_id
            )
        )
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# build_usage_context scoping                                                   #
# --------------------------------------------------------------------------- #


def test_usage_context_partner_scopes_to_org() -> None:
    p = _partner_principal()
    ctx = energy.build_usage_context(
        p, feature_key="jd_extraction", task_type="jd_extraction"
    )
    assert ctx.billing_scope == "org"
    assert ctx.org_id == p.org_id
    assert ctx.actor_persona == "partner"


def test_usage_context_student_scopes_to_user() -> None:
    p = Principal(user_id=uuid.uuid4(), persona="student")
    ctx = energy.build_usage_context(
        p, feature_key="cover_letter", task_type="cover_letter"
    )
    assert ctx.billing_scope == "user"
    assert ctx.org_id is None
    assert ctx.actor_persona == "student"


def test_charge_units_are_cost_weighted() -> None:
    # Vision extraction costs more than a text edit.
    assert energy.charge_units("jd_vision_extraction") > energy.charge_units(
        "cv_edit_command"
    )


# --------------------------------------------------------------------------- #
# generate_json_note metered charging                                           #
# --------------------------------------------------------------------------- #


async def test_json_note_charges_org_on_success(db_session, monkeypatch) -> None:
    async def fake_complete(self, messages, *, temperature=0.2, max_tokens=1024):
        return AICompletion(
            text='{"ok": true}', model_alias="x", usage={}, finish_reason="stop"
        )

    monkeypatch.setattr(tr.AiTaskRunner, "complete", fake_complete)
    p = _partner_principal()
    ctx = energy.build_usage_context(
        p, feature_key="jd_extraction", task_type="jd_extraction"
    )

    data = await llm.generate_json_note(
        system_prompt="s",
        user_content="u",
        task_type="jd_extraction",
        db=db_session,
        user_id=p.user_id,
        org_id=p.org_id,
        usage_context=ctx,
        charge_units=energy.charge_units("jd_extraction"),
    )

    assert data == {"ok": True}
    assert await _org_units(db_session, p.org_id) == energy.charge_units("jd_extraction")
    assert await _ledger_status(db_session, p.org_id) == "success"


async def test_json_note_malformed_records_zero_credits(db_session, monkeypatch) -> None:
    async def fake_complete(self, messages, *, temperature=0.2, max_tokens=1024):
        return AICompletion(
            text="not json at all", model_alias="x", usage={}, finish_reason="stop"
        )

    monkeypatch.setattr(tr.AiTaskRunner, "complete", fake_complete)
    p = _partner_principal()
    ctx = energy.build_usage_context(
        p, feature_key="jd_extraction", task_type="jd_extraction"
    )

    with pytest.raises(AIUnavailableError):
        await llm.generate_json_note(
            system_prompt="s",
            user_content="u",
            task_type="jd_extraction",
            db=db_session,
            user_id=p.user_id,
            org_id=p.org_id,
            usage_context=ctx,
            charge_units=energy.charge_units("jd_extraction"),
        )

    assert await _org_units(db_session, p.org_id) == 0  # nothing billed
    assert await _ledger_status(db_session, p.org_id) == "validation_failed"


async def test_json_note_provider_failure_records_zero(db_session, monkeypatch) -> None:
    async def fake_complete(self, messages, *, temperature=0.2, max_tokens=1024):
        raise AIUnavailableError()

    monkeypatch.setattr(tr.AiTaskRunner, "complete", fake_complete)
    p = _partner_principal()
    ctx = energy.build_usage_context(
        p, feature_key="jd_extraction", task_type="jd_extraction"
    )

    with pytest.raises(AIUnavailableError):
        await llm.generate_json_note(
            system_prompt="s",
            user_content="u",
            task_type="jd_extraction",
            db=db_session,
            user_id=p.user_id,
            org_id=p.org_id,
            usage_context=ctx,
            charge_units=5,
        )

    assert await _org_units(db_session, p.org_id) == 0
    assert await _ledger_status(db_session, p.org_id) == "provider_failed"


# --------------------------------------------------------------------------- #
# generate_note through the real OFFLINE runner: attributes org_id + charges     #
# --------------------------------------------------------------------------- #


async def test_generate_note_offline_logs_org_and_charges(db_session) -> None:
    p = _partner_principal()
    ctx = energy.build_usage_context(
        p, feature_key="jd_writer", task_type="jd_generation"
    )

    text = await llm.generate_note(
        system_prompt="Write a JD",
        user_content="Software Engineer",
        task_type="jd_generation",
        db=db_session,
        user_id=p.user_id,
        org_id=p.org_id,
        usage_context=ctx,
        charge_units=energy.charge_units("jd_writer"),
    )

    assert isinstance(text, str)
    # ai_usage_log row is attributed to the org.
    log_org = (
        await db_session.execute(
            select(AiUsageLog.org_id).where(AiUsageLog.org_id == p.org_id).limit(1)
        )
    ).scalar_one_or_none()
    assert log_org == p.org_id
    # Ledger charged the cost-weighted credits.
    assert await _org_units(db_session, p.org_id) == energy.charge_units("jd_writer")

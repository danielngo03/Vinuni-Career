"""Integration tests for the JD Writer AI service (jd_ai_service).

Covers: draft generation returns a safe advisory draft (offline provider, no
network/keys), the new bias_check field is present and structurally correct,
and a biased partner instruction surfaces requires_human_review without
blocking generation (advisory only, §9.3).

Note: this service previously had zero dedicated tests — this file closes
that gap (found during the AI-EVAL-JD-BENCHMARK1 / bias_detection batches).
"""

from __future__ import annotations

import pytest
from app.modules.opportunities.application import jd_ai_service

from tests.messaging_utils import make_partner


@pytest.mark.asyncio
async def test_draft_standalone_returns_draft_and_bias_check(db_session):
    _user, _org, partner_principal = await make_partner(db_session)

    result = await jd_ai_service.draft_description_standalone(
        db_session,
        principal=partner_principal,
        payload={"title": "Backend Engineer Intern", "employment_type": "internship"},
    )

    assert result["draft"]
    assert isinstance(result["prompt_version"], int)
    assert "bias_check" in result
    assert result["bias_check"]["flagged"] is False
    assert result["bias_check"]["requires_human_review"] is False
    assert result["bias_check"]["findings"] == []


@pytest.mark.asyncio
async def test_draft_standalone_biased_instruction_flags_for_human_review(db_session):
    _user, _org, partner_principal = await make_partner(db_session)

    result = await jd_ai_service.draft_description_standalone(
        db_session,
        principal=partner_principal,
        payload={
            "title": "Office Assistant",
            "partner_instruction": "Chỉ tuyển nam, dưới 30 tuổi, không khuyết tật.",
        },
    )

    # The offline provider echoes the (sanitized) instruction back into the
    # draft, so the bias checker — which scans the DRAFT TEXT, not the raw
    # input — flags it exactly as it would flag a real generated draft.
    assert result["bias_check"]["flagged"] is True
    assert result["bias_check"]["requires_human_review"] is True
    categories = {f["category"] for f in result["bias_check"]["findings"]}
    assert "gender_exclusion" in categories


@pytest.mark.asyncio
async def test_draft_standalone_requires_partner_permission(db_session):
    from app.shared.exceptions import AuthRequiredError
    from app.shared.permissions import GUEST

    with pytest.raises(AuthRequiredError):
        await jd_ai_service.draft_description_standalone(
            db_session,
            principal=GUEST,
            payload={"title": "Backend Engineer"},
        )


@pytest.mark.asyncio
async def test_draft_standalone_never_leaks_provider_or_model():
    """No DB/network needed — a quick guard-rail smoke test on the response text."""
    import uuid

    from app.shared.permissions import Principal

    principal = Principal(
        user_id=uuid.uuid4(),
        persona="partner_user",
        permissions=frozenset({"jobs:create"}),
    )
    result = await jd_ai_service.draft_description_standalone(
        None,  # type: ignore[arg-type]  # standalone path does not query the DB
        principal=principal,
        payload={"title": "Data Analyst"},
    )
    lowered = result["draft"].lower()
    for term in ("openrouter", "openai", "anthropic", "gpt-4", "model_alias"):
        assert term not in lowered

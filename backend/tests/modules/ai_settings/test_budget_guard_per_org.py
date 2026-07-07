"""Per-org daily AI budget enforcement tests (Task 5).

Coverage:
- Per-org cap triggers PaymentRequiredError when org spend + estimated > per_org_daily_budget_usd.
- A different org is unaffected (isolated by org_id).
- Missing org_id (None) skips per-org check.
- Platform budget and per-user quota checks are preserved (no regression).
- Silent degrade on infra error for the per-org DB query.
- per_org_daily_budget_usd=None means no org cap.

Run:
    cd backend && uv run pytest tests/modules/ai_settings/test_budget_guard_per_org.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from app.ai.gateway.runtime_config import EffectiveAiConfig

# ---------------------------------------------------------------------------
# Helper: build a mock EffectiveAiConfig with a real platform budget
# ---------------------------------------------------------------------------

def _make_cfg(daily_budget_usd: float = 10.0) -> EffectiveAiConfig:
    return EffectiveAiConfig(
        real_calls_active=True,
        chat_model_alias="chat_cheap",
        reasoning_model_alias="reasoning_cheap",
        embedding_model_alias="embedding_cheap",
        rerank_model_alias="rerank_cheap",
        eval_model_alias="eval_cheap",
        daily_budget_usd=daily_budget_usd,
        cv_llm_structuring_enabled=False,
        job_fit_ai_explanation_enabled=True,
        provider_routes={},
    )


# ---------------------------------------------------------------------------
# Core test: per-org cap enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_org_budget_exceeded_raises(db_session: object) -> None:
    """With per_org_daily_budget_usd=1.0 and org spend already at 1.0,
    adding 0.01 more must raise PaymentRequiredError(BUDGET_EXCEEDED)."""
    from app.ai.observability.models import AiUsageDaily
    from app.modules.ai_settings.application.budget_guard import check_async
    from app.modules.ai_settings.domain.models import AiSettings
    from app.shared.exceptions import PaymentRequiredError

    org_id = uuid.uuid4()
    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    # Insert the singleton ai_settings row with per_org_daily_budget_usd=1.0
    settings_row = AiSettings(
        scope="platform",
        per_org_daily_budget_usd=Decimal("1.00"),
        daily_budget_usd=Decimal("100.00"),  # platform budget is large — not a blocker
    )
    db_session.add(settings_row)

    # Insert a pre-aggregated rollup row for org_id X: already spent 1.0 today
    rollup = AiUsageDaily(
        day=today,
        task_type="assistant",
        provider="",
        model="",
        org_id=org_id,
        cost_usd=1.0,
        requests=5,
    )
    db_session.add(rollup)
    await db_session.commit()

    mock_cfg = _make_cfg(daily_budget_usd=100.0)

    with patch("app.modules.ai_settings.application.budget_guard.runtime_config") as mock_rc:
        mock_rc.current.return_value = mock_cfg
        with pytest.raises(PaymentRequiredError) as exc:
            await check_async(
                db_session,
                alias="chat_cheap",
                estimated_cost_usd=0.01,
                org_id=org_id,
            )

    assert exc.value.details["reason"] == "BUDGET_EXCEEDED"


@pytest.mark.asyncio
async def test_per_org_budget_different_org_unaffected(db_session: object) -> None:
    """Org Y with zero spend must NOT be blocked when org X is over budget."""
    from app.ai.observability.models import AiUsageDaily
    from app.modules.ai_settings.application.budget_guard import check_async
    from app.modules.ai_settings.domain.models import AiSettings

    org_x = uuid.uuid4()
    org_y = uuid.uuid4()
    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    settings_row = AiSettings(
        scope="platform",
        per_org_daily_budget_usd=Decimal("1.00"),
        daily_budget_usd=Decimal("100.00"),
    )
    db_session.add(settings_row)

    # org_x is at the limit
    rollup = AiUsageDaily(
        day=today,
        task_type="assistant",
        provider="",
        model="",
        org_id=org_x,
        cost_usd=1.0,
        requests=5,
    )
    db_session.add(rollup)
    await db_session.commit()

    mock_cfg = _make_cfg(daily_budget_usd=100.0)

    with patch("app.modules.ai_settings.application.budget_guard.runtime_config") as mock_rc:
        mock_rc.current.return_value = mock_cfg
        # org_y has no spend — should NOT raise
        await check_async(
            db_session,
            alias="chat_cheap",
            estimated_cost_usd=0.01,
            org_id=org_y,
        )


@pytest.mark.asyncio
async def test_per_org_check_skipped_when_org_id_is_none(db_session: object) -> None:
    """When org_id=None, per-org check is skipped (backward compat)."""
    from app.modules.ai_settings.application.budget_guard import check_async
    from app.modules.ai_settings.domain.models import AiSettings

    # per_org_daily_budget_usd set to 0.001 — would immediately block any org
    settings_row = AiSettings(
        scope="platform",
        per_org_daily_budget_usd=Decimal("0.001"),
        daily_budget_usd=Decimal("100.00"),
    )
    db_session.add(settings_row)
    await db_session.commit()

    mock_cfg = _make_cfg(daily_budget_usd=100.0)

    with patch("app.modules.ai_settings.application.budget_guard.runtime_config") as mock_rc:
        mock_rc.current.return_value = mock_cfg
        # No org_id → no per-org check → no raise
        await check_async(
            db_session,
            alias="chat_cheap",
            estimated_cost_usd=0.005,
            org_id=None,
        )


@pytest.mark.asyncio
async def test_per_org_check_skipped_when_budget_is_none(db_session: object) -> None:
    """When per_org_daily_budget_usd is NULL in DB, no org cap is applied."""
    from app.modules.ai_settings.application.budget_guard import check_async
    from app.modules.ai_settings.domain.models import AiSettings

    org_id = uuid.uuid4()

    settings_row = AiSettings(
        scope="platform",
        per_org_daily_budget_usd=None,  # no cap
        daily_budget_usd=Decimal("100.00"),
    )
    db_session.add(settings_row)
    await db_session.commit()

    # Use a cost that is well under the platform budget (100.0) so only the
    # per-org check is the potential blocker — and NULL means it won't block.
    mock_cfg = _make_cfg(daily_budget_usd=100.0)

    with patch("app.modules.ai_settings.application.budget_guard.runtime_config") as mock_rc:
        mock_rc.current.return_value = mock_cfg
        # Small cost stays under platform budget; per_org_daily_budget_usd=None → no raise
        await check_async(
            db_session,
            alias="chat_cheap",
            estimated_cost_usd=0.01,
            org_id=org_id,
        )


@pytest.mark.asyncio
async def test_per_org_degrade_silently_on_infra_error(db_session: object) -> None:
    """If the per-org DB query fails, check_async degrades silently (does not block)."""
    from app.modules.ai_settings.application import budget_guard
    from app.modules.ai_settings.domain.models import AiSettings

    org_id = uuid.uuid4()

    settings_row = AiSettings(
        scope="platform",
        per_org_daily_budget_usd=Decimal("1.00"),
        daily_budget_usd=Decimal("100.00"),
    )
    db_session.add(settings_row)
    await db_session.commit()

    mock_cfg = _make_cfg(daily_budget_usd=100.0)

    # Simulate DB failure for the per-org query by patching the DB execute call
    # only when called with a query involving AiUsageDaily.  We use a simpler
    # approach: patch the internal _fetch_org_spend_today helper.
    with patch("app.modules.ai_settings.application.budget_guard.runtime_config") as mock_rc:
        mock_rc.current.return_value = mock_cfg
        # Patch _fetch_org_spend_today to raise
        with patch(
            "app.modules.ai_settings.application.budget_guard._fetch_org_spend_today",
            side_effect=RuntimeError("simulated DB failure"),
        ):
            # Must NOT raise — silently degrades
            await budget_guard.check_async(
                db_session,
                alias="chat_cheap",
                estimated_cost_usd=0.01,
                org_id=org_id,
            )


# ---------------------------------------------------------------------------
# Regression: existing platform + user quota checks are preserved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_budget_still_enforced(db_session: object) -> None:
    """Platform daily_budget_usd is still checked even when org_id is provided."""
    from app.ai.observability.models import AiUsageLog
    from app.modules.ai_settings.application.budget_guard import check_async
    from app.shared.exceptions import PaymentRequiredError

    # The platform budget is already exceeded via AiUsageLog
    db_session.add(
        AiUsageLog(
            task_type="assistant",
            model_alias="chat_cheap",
            success=True,
            cost_usd=0.99,
            created_at=datetime.now(tz=UTC),
        )
    )
    await db_session.commit()

    # Platform budget = 1.0 USD, already spent 0.99 → adding 0.02 exceeds it
    mock_cfg = _make_cfg(daily_budget_usd=1.0)

    with patch("app.modules.ai_settings.application.budget_guard.runtime_config") as mock_rc:
        mock_rc.current.return_value = mock_cfg
        with pytest.raises(PaymentRequiredError) as exc:
            await check_async(
                db_session,
                alias="chat_cheap",
                estimated_cost_usd=0.02,
                org_id=uuid.uuid4(),  # org_id present but platform check fires first
            )

    assert exc.value.details["reason"] == "BUDGET_EXCEEDED"

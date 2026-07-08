"""Tests for the AI energy meter (`usage_service` over `ai.energy.service`).

The user-facing unit is an **energy %** derived from cost-weighted credits summed
from the durable ``ai_billable_usage`` ledger. Windows: weekly = HARD block
(after the top-up wallet); 3h rolling = SOFT warn only; NO daily gate. A partner
member meters on the shared ORG pool; a student on their own user scope.

Covers: empty state, per-scope counting, the 80% warning, weekly exhaustion
blocking + the 409 gate, the 3h burst soft-warn, the non-resetting wallet, and
the leakage-safe detail breakdown — all against real ledger rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.ai.energy.models import AiEnergyAccount
from app.ai.observability.billable_usage import (
    PERSONA_PARTNER,
    PERSONA_STUDENT,
    RESULT_SUCCESS,
    SCOPE_ORG,
    SCOPE_USER,
)
from app.ai.observability.models import AiBillableUsage, AiUsageLog
from app.modules.ai_assistant.application import usage_service
from app.shared.exceptions import QuotaExceededError
from app.shared.permissions import Principal

from tests.auth_utils import register_verified

# Persona defaults (see app.ai.energy.constants).
STUDENT_WEEKLY = 120
PARTNER_ORG_WEEKLY = 400


async def _charge(
    db_session,
    *,
    units: int,
    org_id=None,
    user_id=None,
    persona: str = PERSONA_PARTNER,
    scope: str = SCOPE_ORG,
    feature: str = "chatbot",
    created_at=None,
    result: str = RESULT_SUCCESS,
) -> None:
    db_session.add(
        AiBillableUsage(
            actor_persona=persona,
            billing_scope=scope,
            feature_key=feature,
            task_type="x",
            result_status=result,
            units_charged=units,
            org_id=org_id,
            actor_user_id=user_id,
            created_at=created_at or datetime.now(UTC),
        )
    )
    await db_session.flush()


async def _student(db_session) -> Principal:
    user = await register_verified(
        db_session, email=f"energy_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    return Principal(user_id=user.id, persona=PERSONA_STUDENT, permissions=frozenset())


async def _partner(db_session) -> Principal:
    user = await register_verified(
        db_session, email=f"energy_p_{uuid.uuid4().hex[:8]}@corp.example.com"
    )
    return Principal(
        user_id=user.id,
        persona="partner_member",
        org_id=uuid.uuid4(),
        permissions=frozenset(),
    )


# --------------------------------------------------------------------------- #
# Snapshot shape + empty state                                                  #
# --------------------------------------------------------------------------- #


async def test_energy_empty_is_full_and_unblocked(db_session) -> None:
    principal = await _student(db_session)

    data = await usage_service.my_usage(db_session, principal=principal)

    assert data["scope"] == "user"
    assert data["energy_pct"] == 100
    assert data["weekly"]["used"] == 0
    assert data["weekly"]["allowance"] == STUDENT_WEEKLY
    assert data["blocked"] is False
    assert data["warning"] is False
    # No daily window anywhere in the shape.
    assert "day" not in data
    datetime.fromisoformat(data["week_reset"])  # parseable


async def test_partner_meters_on_org_pool(db_session) -> None:
    principal = await _partner(db_session)
    assert principal.org_id is not None

    # Another member's spend on the SAME org counts against the shared pool.
    await _charge(db_session, units=100, org_id=principal.org_id, user_id=uuid.uuid4())

    data = await usage_service.my_usage(db_session, principal=principal)

    assert data["scope"] == "org"
    assert data["weekly"]["used"] == 100
    assert data["weekly"]["allowance"] == PARTNER_ORG_WEEKLY
    assert data["energy_pct"] == 75  # (400-100)/400


async def test_energy_counts_only_my_scope(db_session) -> None:
    principal = await _student(db_session)
    # Rows for a different user must not count.
    await _charge(
        db_session, units=50, user_id=uuid.uuid4(), persona=PERSONA_STUDENT,
        scope=SCOPE_USER,
    )
    await _charge(
        db_session, units=30, user_id=principal.user_id, persona=PERSONA_STUDENT,
        scope=SCOPE_USER,
    )
    # Last week: outside the weekly window.
    await _charge(
        db_session, units=40, user_id=principal.user_id, persona=PERSONA_STUDENT,
        scope=SCOPE_USER, created_at=datetime.now(UTC) - timedelta(days=8),
    )

    data = await usage_service.my_usage(db_session, principal=principal)
    assert data["weekly"]["used"] == 30


# --------------------------------------------------------------------------- #
# Warning + weekly hard block + the 409 gate                                     #
# --------------------------------------------------------------------------- #


async def test_warns_at_80_percent_weekly(db_session) -> None:
    principal = await _student(db_session)
    await _charge(
        db_session, units=int(STUDENT_WEEKLY * 0.8), user_id=principal.user_id,
        persona=PERSONA_STUDENT, scope=SCOPE_USER,
    )
    data = await usage_service.my_usage(db_session, principal=principal)
    assert data["warning"] is True
    assert data["blocked"] is False


async def test_weekly_exhaustion_blocks_student_and_gates(db_session) -> None:
    principal = await _student(db_session)
    await _charge(
        db_session, units=STUDENT_WEEKLY, user_id=principal.user_id,
        persona=PERSONA_STUDENT, scope=SCOPE_USER,
    )

    data = await usage_service.my_usage(db_session, principal=principal)
    assert data["blocked"] is True
    assert data["energy_pct"] == 0
    assert data["blocked_reason"] == "AI_WEEKLY_ENERGY_EXCEEDED"

    with pytest.raises(QuotaExceededError) as exc:
        await usage_service.enforce_quota(db_session, principal=principal)
    assert exc.value.details["reason"] == "AI_WEEKLY_ENERGY_EXCEEDED"


async def test_org_weekly_exhaustion_blocks_and_gates(db_session) -> None:
    principal = await _partner(db_session)
    await _charge(
        db_session, units=PARTNER_ORG_WEEKLY, org_id=principal.org_id,
        user_id=uuid.uuid4(),
    )

    data = await usage_service.my_usage(db_session, principal=principal)
    assert data["blocked"] is True
    assert data["blocked_reason"] == "AI_ORG_WEEKLY_ENERGY_EXCEEDED"

    with pytest.raises(QuotaExceededError) as exc:
        await usage_service.enforce_quota(db_session, principal=principal)
    assert exc.value.details["reason"] == "AI_ORG_WEEKLY_ENERGY_EXCEEDED"
    assert exc.value.details["scope"] == "org"


# --------------------------------------------------------------------------- #
# 3h burst (soft) + wallet (non-resetting top-up)                               #
# --------------------------------------------------------------------------- #


async def test_3h_burst_warns_but_never_blocks(db_session) -> None:
    principal = await _student(db_session)
    # soft_cap = 0.4 * 120 = 48. Spend 50 in the last 3h — over the burst cap but
    # well under the weekly allowance.
    await _charge(
        db_session, units=50, user_id=principal.user_id, persona=PERSONA_STUDENT,
        scope=SCOPE_USER,
    )
    data = await usage_service.my_usage(db_session, principal=principal)
    assert data["session_3h"]["used"] == 50
    assert data["session_3h"]["over_soft_cap"] is True
    assert data["warning"] is True
    assert data["blocked"] is False  # 3h NEVER blocks


async def test_wallet_extends_capacity_before_blocking(db_session) -> None:
    principal = await _partner(db_session)
    # Org has spent its full weekly allowance...
    await _charge(
        db_session, units=PARTNER_ORG_WEEKLY, org_id=principal.org_id,
        user_id=uuid.uuid4(),
    )
    # ...but a purchased wallet of 100 credits keeps it unblocked.
    db_session.add(
        AiEnergyAccount(
            scope_type="org", scope_id=principal.org_id, org_id=principal.org_id,
            wallet_units=100,
        )
    )
    await db_session.flush()

    data = await usage_service.my_usage(db_session, principal=principal)
    assert data["weekly"]["wallet"] == 100
    assert data["weekly"]["capacity"] == PARTNER_ORG_WEEKLY + 100
    assert data["blocked"] is False

    # Spend the wallet too → now blocked.
    await _charge(
        db_session, units=100, org_id=principal.org_id, user_id=uuid.uuid4()
    )
    data = await usage_service.my_usage(db_session, principal=principal)
    assert data["blocked"] is True


async def test_org_account_allowance_override(db_session) -> None:
    principal = await _partner(db_session)
    db_session.add(
        AiEnergyAccount(
            scope_type="org", scope_id=principal.org_id, org_id=principal.org_id,
            weekly_allowance_units=1000,
        )
    )
    await db_session.flush()

    data = await usage_service.my_usage(db_session, principal=principal)
    assert data["weekly"]["allowance"] == 1000


# --------------------------------------------------------------------------- #
# Detail view breakdown (from ai_usage_log) — leakage-safe                       #
# --------------------------------------------------------------------------- #


async def _log(db_session, *, user_id=None, org_id=None, task_type, n=1, success=True):
    for _ in range(n):
        db_session.add(
            AiUsageLog(
                task_type=task_type,
                model_alias="chat_cheap",
                success=success,
                user_id=user_id,
                org_id=org_id,
                created_at=datetime.now(UTC),
            )
        )
    await db_session.flush()


async def test_detail_breakdown_maps_tasks_to_features(db_session) -> None:
    principal = await _student(db_session)
    await _log(db_session, user_id=principal.user_id, task_type="ai_assistant_chat", n=3)
    await _log(db_session, user_id=principal.user_id, task_type="cover_letter", n=2)
    await _log(db_session, user_id=principal.user_id, task_type="kb_embedding", n=2)

    data = await usage_service.my_usage_detail(db_session, principal=principal)
    assert data["total"] == 7  # includes excluded system tasks
    features = {r["feature"]: r["count"] for r in data["by_feature"]}
    assert features == {"assistant": 3, "cover_letter": 2}
    assert "day" not in data
    datetime.fromisoformat(data["week_reset"])


async def test_detail_partner_breakdown_is_org_scoped(db_session) -> None:
    principal = await _partner(db_session)
    # Two different members of the same org.
    await _log(db_session, org_id=principal.org_id, task_type="jd_extraction", n=2)
    await _log(db_session, org_id=principal.org_id, task_type="screening_brief", n=1)
    # A row for a DIFFERENT org must not count.
    await _log(db_session, org_id=uuid.uuid4(), task_type="jd_extraction", n=5)

    data = await usage_service.my_usage_detail(db_session, principal=principal)
    features = {r["feature"]: r["count"] for r in data["by_feature"]}
    assert features == {"jd_import": 2, "screening": 1}


async def test_detail_never_leaks_ai_internals(db_session) -> None:
    import json

    principal = await _student(db_session)
    await _log(db_session, user_id=principal.user_id, task_type="cover_letter", n=2)
    await _log(db_session, user_id=principal.user_id, task_type="cv_vision_extraction", n=1)

    data = await usage_service.my_usage_detail(db_session, principal=principal)
    blob = json.dumps(data, ensure_ascii=False).lower()
    for term in (
        "chat_cheap", "model_alias", "usd", "token", "prompt", "latency",
        "openrouter", "openai", "gemini", "gpt", "claude",
        "cv_vision_extraction", "ai_assistant_chat",
    ):
        assert term not in blob, f"leaked term: {term!r}"


# --------------------------------------------------------------------------- #
# The chat gate refuses when energy is exhausted                                #
# --------------------------------------------------------------------------- #


async def test_chat_send_message_refused_when_energy_exhausted(db_session) -> None:
    from app.modules.ai_assistant.application import chat_service

    principal = await _student(db_session)
    created = await chat_service.create_session(db_session, principal=principal)
    await _charge(
        db_session, units=STUDENT_WEEKLY, user_id=principal.user_id,
        persona=PERSONA_STUDENT, scope=SCOPE_USER,
    )

    with pytest.raises(QuotaExceededError):
        await chat_service.send_message(
            db_session,
            principal=principal,
            session_id=uuid.UUID(created["id"]),
            text="Xin chào",
        )

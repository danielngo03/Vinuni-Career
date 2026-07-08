"""ai_settings admin service tests (ADR-0011 first slice).

Covers: singleton seed on first read; masked GET (alias + flags + budget + derived
status, NO key/base_url/provider/model/token); PATCH updates aliases/flags/budget
with an audited before/after diff; alias allowlist rejection (422 — no model-path
injection); the kill switch; and RBAC (partner / no-permission → 403, university
admin + superadmin → ok). The env-ceiling precedence proof lives in
``test_ai_settings_resolver.py``.
"""

from __future__ import annotations

import json
import uuid

import pytest
from app.ai.gateway import runtime_config
from app.ai.gateway.factory import _get_api_key
from app.ai.gateway.provider_key_crypto import decrypt_provider_api_key
from app.ai.gateway.provider_models import AiProviderConfig
from app.ai.gateway.provider_registry import create_alias, create_provider
from app.core.config import get_settings
from app.modules.ai_settings.application import resolver, settings_service
from app.modules.ai_settings.domain.models import ROLLOUT_ENABLED
from app.shared.exceptions import PermissionDeniedError, ValidationFailedError
from app.shared.models import AuditLog
from app.shared.permissions import Principal
from sqlalchemy import func, select

from tests.auth_utils import CTX, register_verified
from tests.org_utils import make_org_with_admin

# Secrets / internals that must NEVER appear in any admin response.
_FORBIDDEN_SUBSTRINGS = (
    "openrouter_api_key",
    "openai_compatible_base_url",
    "base_url",
    "api_key",
    "openrouter.ai",
    "deepseek",
    "text-embedding",
    "gpt-4",
    "token",
    "usage",
    "latency",
)


@pytest.fixture(autouse=True)
def _reset_runtime_snapshot():
    """Each test starts/ends in env-bootstrap mode (no leaked published snapshot)."""

    runtime_config.reset_to_bootstrap()
    yield
    runtime_config.reset_to_bootstrap()


async def _university_admin(db):
    _user, _org, principal = await make_org_with_admin(
        db, org_type="university", display_name="VinUni"
    )
    return principal


async def _partner_admin(db):
    _user, _org, principal = await make_org_with_admin(
        db, org_type="partner", display_name="Acme Corp"
    )
    return principal


async def _superadmin(db):
    user = await register_verified(db, email=f"root_{uuid.uuid4().hex[:8]}@vinuni.edu.vn")
    return Principal(user_id=user.id, persona="staff", is_superadmin=True)


async def _no_permission_user(db):
    user = await register_verified(db, email=f"stu_{uuid.uuid4().hex[:8]}@vinuni.edu.vn")
    return Principal(user_id=user.id, persona="student", permissions=frozenset())


def _assert_no_secret_leak(payload: dict) -> None:
    blob = json.dumps(payload, default=str).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle not in blob, f"secret/internal leaked: {needle!r}"


# --------------------------------------------------------------------------- #
# Seed + masked GET                                                           #
# --------------------------------------------------------------------------- #


async def test_get_seeds_singleton_and_returns_masked_view(db_session) -> None:
    principal = await _university_admin(db_session)
    view = await settings_service.get_effective_settings(db_session, principal=principal)

    # Exactly one platform row exists after the lazy seed.
    from app.modules.ai_settings.domain.models import AiSettings

    count = (
        await db_session.execute(select(func.count()).select_from(AiSettings))
    ).scalar_one()
    assert count == 1

    # Alias names + flags + budget + DERIVED status are present.
    assert view["models"] == {
        "chat": "chat_default",
        "reasoning": "reasoning_default",
        "embedding": "embedding_default",
        "rerank": "rerank_default",
        "eval": "eval_default",
    }
    assert view["feature_flags"]["job_fit_ai_explanation_enabled"] is True
    assert view["feature_flags"]["cv_llm_structuring_enabled"] is False
    assert view["daily_budget_usd"] == "1.00"
    assert "chat_default" in view["allowed_aliases"]["chat"]
    assert "rerank_default" in view["allowed_aliases"]["rerank"]
    # Derived status only: no key in the test env -> offline + key_configured False.
    assert view["key_configured"] is False
    assert view["real_calls"] == "offline"
    _assert_no_secret_leak(view)


async def test_get_is_idempotent_singleton(db_session) -> None:
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)
    await settings_service.get_effective_settings(db_session, principal=principal)

    from app.modules.ai_settings.domain.models import AiSettings

    count = (
        await db_session.execute(select(func.count()).select_from(AiSettings))
    ).scalar_one()
    assert count == 1


# --------------------------------------------------------------------------- #
# PATCH: aliases / flags / budget + audited diff                              #
# --------------------------------------------------------------------------- #


async def test_patch_updates_flags_budget_and_audits_diff(db_session) -> None:
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)

    view = await settings_service.update_settings(
        db_session,
        principal=principal,
        payload={
            "cv_llm_structuring_enabled": True,
            "daily_budget_usd": "2.50",
            "rollout_state": "paused",
        },
        ctx=CTX,
    )
    assert view["feature_flags"]["cv_llm_structuring_enabled"] is True
    assert view["daily_budget_usd"] == "2.50"
    assert view["rollout_state"] == "paused"
    _assert_no_secret_leak(view)

    # An audit row with a before/after diff was written (no secret in the diff).
    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "ai_settings.updated")
        )
    ).scalars().all()
    assert len(audit) == 1
    entry = audit[0]
    assert entry.after_snapshot["cv_llm_structuring_enabled"] is True
    assert entry.after_snapshot["daily_budget_usd"] == "2.50"
    assert entry.before_snapshot["cv_llm_structuring_enabled"] is False
    _assert_no_secret_leak(
        {"before": entry.before_snapshot, "after": entry.after_snapshot}
    )


async def test_patch_publishes_snapshot_to_gateway(db_session) -> None:
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)
    assert runtime_config.current().cv_llm_structuring_enabled is False

    await settings_service.update_settings(
        db_session,
        principal=principal,
        payload={"cv_llm_structuring_enabled": True},
        ctx=CTX,
    )
    # The rewired consumer reads the published snapshot.
    assert runtime_config.current().cv_llm_structuring_enabled is True


async def test_provider_key_is_encrypted_and_drives_runtime_snapshot(
    db_session, monkeypatch
) -> None:
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)

    provider = await create_provider(
        db_session,
        payload={
            "name": "campus-ai",
            "provider_type": "openai_compatible",
            "base_url": "https://ai.example.edu/v1",
            "api_key": "sk-campus-secret",
            "description": "Campus managed key",
        },
        created_by=principal.user_id,
    )
    assert provider["has_api_key"] is True
    assert "api_key" not in provider

    row = (
        await db_session.execute(
            select(AiProviderConfig).where(AiProviderConfig.name == "campus-ai")
        )
    ).scalar_one()
    assert row.api_key_ciphertext
    assert row.api_key_ciphertext != "sk-campus-secret"
    assert "sk-campus-secret" not in row.api_key_ciphertext
    assert decrypt_provider_api_key(row.api_key_ciphertext) == "sk-campus-secret"

    alias = await create_alias(
        db_session,
        payload={
            "alias_name": "chat_campus",
            "model_id": "campus-chat-model",
            "provider_id": provider["id"],
            "task_families": "chat,reasoning,embedding,rerank,eval",
            "description": "Campus all-family smoke alias",
        },
        created_by=principal.user_id,
    )
    assert alias["provider_name"] == "campus-ai"
    await db_session.commit()

    from app.modules.ai_settings.infrastructure import repository

    settings = await repository.get_or_create_platform(db_session)
    settings.real_calls_enabled = True
    settings.rollout_state = ROLLOUT_ENABLED
    settings.chat_model_alias = "chat_campus"
    settings.reasoning_model_alias = "chat_campus"
    settings.embedding_model_alias = "chat_campus"
    settings.rerank_model_alias = "chat_campus"
    settings.eval_model_alias = "chat_campus"
    await db_session.commit()

    monkeypatch.setenv("AI_REAL_CALLS_ENABLED", "true")
    get_settings.cache_clear()
    cfg = await resolver.resolve_and_publish(db_session)
    assert cfg.real_calls_active is True
    assert cfg.provider_key_ciphertexts["campus-ai"] == row.api_key_ciphertext
    assert "sk-campus-secret" not in str(cfg.provider_key_ciphertexts)
    assert _get_api_key("campus-ai") == "sk-campus-secret"
    get_settings.cache_clear()


async def test_patch_rejects_alias_outside_allowlist(db_session) -> None:
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)

    with pytest.raises(ValidationFailedError):
        await settings_service.update_settings(
            db_session,
            principal=principal,
            payload={"chat_model_alias": "openai/gpt-4o"},  # raw model-path injection
            ctx=CTX,
        )


async def test_patch_rejects_invalid_rollout_state(db_session) -> None:
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)
    with pytest.raises(ValidationFailedError):
        await settings_service.update_settings(
            db_session, principal=principal,
            payload={"rollout_state": "yolo"}, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Kill switch                                                                  #
# --------------------------------------------------------------------------- #


async def test_disable_ai_kill_switch(db_session) -> None:
    principal = await _university_admin(db_session)
    # Persist real_calls_enabled=true first (inert without env+key, but the kill
    # switch must still force it back off + rollout offline).
    await settings_service.get_effective_settings(db_session, principal=principal)
    await settings_service.update_settings(
        db_session, principal=principal,
        payload={"real_calls_enabled": True}, ctx=CTX,
    )

    view = await settings_service.disable_ai(db_session, principal=principal, ctx=CTX)
    assert view["real_calls_enabled"] is False
    assert view["rollout_state"] == "offline"
    assert view["real_calls"] == "offline"

    audit = (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "ai_settings.disabled"
            )
        )
    ).scalar_one()
    assert audit == 1


# --------------------------------------------------------------------------- #
# RBAC                                                                         #
# --------------------------------------------------------------------------- #


async def test_superadmin_can_read_and_update(db_session) -> None:
    principal = await _superadmin(db_session)
    view = await settings_service.get_effective_settings(db_session, principal=principal)
    assert view["scope"] == "platform"
    view = await settings_service.update_settings(
        db_session, principal=principal,
        payload={"job_fit_ai_explanation_enabled": False}, ctx=CTX,
    )
    assert view["feature_flags"]["job_fit_ai_explanation_enabled"] is False


async def test_partner_admin_forbidden(db_session) -> None:
    principal = await _partner_admin(db_session)  # has *:* but partner org_type
    with pytest.raises(PermissionDeniedError):
        await settings_service.get_effective_settings(db_session, principal=principal)
    with pytest.raises(PermissionDeniedError):
        await settings_service.update_settings(
            db_session, principal=principal,
            payload={"cv_llm_structuring_enabled": True}, ctx=CTX,
        )


async def test_no_permission_user_forbidden(db_session) -> None:
    principal = await _no_permission_user(db_session)
    with pytest.raises(PermissionDeniedError):
        await settings_service.get_effective_settings(db_session, principal=principal)
    with pytest.raises(PermissionDeniedError):
        await settings_service.disable_ai(db_session, principal=principal, ctx=CTX)


# --------------------------------------------------------------------------- #
# per_org_daily_budget_usd: GET returns it, PATCH sets it, negative rejected  #
# --------------------------------------------------------------------------- #


async def test_get_returns_per_org_budget_null_by_default(db_session) -> None:
    """GET /admin/ai-settings includes per_org_daily_budget_usd; default is null."""
    principal = await _university_admin(db_session)
    view = await settings_service.get_effective_settings(db_session, principal=principal)

    assert "per_org_daily_budget_usd" in view
    assert view["per_org_daily_budget_usd"] is None
    _assert_no_secret_leak(view)


async def test_patch_sets_per_org_budget_and_get_returns_it(db_session) -> None:
    """PATCH per_org_daily_budget_usd=0.75 persists and is returned on GET."""
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)

    view = await settings_service.update_settings(
        db_session,
        principal=principal,
        payload={"per_org_daily_budget_usd": "0.75"},
        ctx=CTX,
    )
    assert view["per_org_daily_budget_usd"] == "0.75"

    # GET must also reflect the persisted value.
    view2 = await settings_service.get_effective_settings(db_session, principal=principal)
    assert view2["per_org_daily_budget_usd"] == "0.75"
    _assert_no_secret_leak(view2)

    # An audit row must have been written.
    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "ai_settings.updated")
        )
    ).scalars().all()
    assert any(
        row.after_snapshot.get("per_org_daily_budget_usd") == "0.75"
        for row in audit
    )


async def test_patch_clears_per_org_budget(db_session) -> None:
    """clear_per_org_budget=True resets the cap to null."""
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)

    await settings_service.update_settings(
        db_session,
        principal=principal,
        payload={"per_org_daily_budget_usd": "1.00"},
        ctx=CTX,
    )

    view = await settings_service.update_settings(
        db_session,
        principal=principal,
        payload={"clear_per_org_budget": True},
        ctx=CTX,
    )
    assert view["per_org_daily_budget_usd"] is None


async def test_patch_negative_per_org_budget_rejected(db_session) -> None:
    """Negative per_org_daily_budget_usd must return 422 (ValidationFailedError)."""
    from app.shared.exceptions import ValidationFailedError

    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)

    with pytest.raises(ValidationFailedError) as exc_info:
        await settings_service.update_settings(
            db_session,
            principal=principal,
            payload={"per_org_daily_budget_usd": "-0.01"},
            ctx=CTX,
        )
    assert exc_info.value.details["field"] == "per_org_daily_budget_usd"
    assert exc_info.value.details["reason"] == "out_of_range"

"""DB-backed provider fallback-chain resolution (AI_PRODUCT_SPEC §5.2).

Covers:
- Admin can configure an ORDERED fallback provider list on a model alias.
- ``load_active_route_chains`` resolves it to (provider_name, base_url, model_id)
  hops, in order, reusing the alias's model_id.
- Unknown/inactive fallback provider names are dropped, not fatal.
- Built-in aliases with no configured fallback still resolve to a length-1 chain.
- The resolver publishes ``provider_route_chains`` into the runtime snapshot.
"""

from __future__ import annotations

import uuid

from app.ai.gateway import provider_registry
from app.ai.gateway.provider_registry import create_alias, create_provider, update_alias
from app.ai.gateway.provider_route_chains import load_active_route_chains
from app.modules.ai_settings.application import resolver, settings_service

from tests.org_utils import make_org_with_admin


async def _university_admin(db_session):
    return (await make_org_with_admin(db_session, org_type="university"))[2]


async def test_alias_with_no_fallback_resolves_to_single_hop_chain(db_session) -> None:
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)
    await provider_registry.ensure_defaults(db_session)
    await db_session.commit()

    chains = await load_active_route_chains(db_session)

    assert chains["chat_cheap"] == [
        ("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat")
    ]


async def test_configured_fallback_chain_resolves_in_order(db_session) -> None:
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)
    await provider_registry.ensure_defaults(db_session)

    primary = await create_provider(
        db_session,
        payload={
            "name": "campus-primary",
            "base_url": "https://ai-primary.example.edu/v1",
            "api_key": "sk-primary",
        },
        created_by=principal.user_id,
    )
    await create_provider(
        db_session,
        payload={
            "name": "campus-secondary",
            "base_url": "https://ai-secondary.example.edu/v1",
            "api_key": "sk-secondary",
        },
        created_by=principal.user_id,
    )
    await db_session.flush()

    alias = await create_alias(
        db_session,
        payload={
            "alias_name": "chat_campus_chain",
            "model_id": "campus-chat-model",
            "provider_id": primary["id"],
            "task_families": "chat",
            "fallback_provider_names": ["campus-secondary", "openrouter"],
        },
        created_by=principal.user_id,
    )
    assert alias["fallback_provider_names"] == ["campus-secondary", "openrouter"]
    await db_session.commit()

    chains = await load_active_route_chains(db_session)

    assert chains["chat_campus_chain"] == [
        ("campus-primary", "https://ai-primary.example.edu/v1", "campus-chat-model"),
        ("campus-secondary", "https://ai-secondary.example.edu/v1", "campus-chat-model"),
        ("openrouter", "https://openrouter.ai/api/v1", "campus-chat-model"),
    ]


async def test_unknown_fallback_provider_name_is_dropped_not_fatal(db_session) -> None:
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)
    await provider_registry.ensure_defaults(db_session)

    primary = await create_provider(
        db_session,
        payload={
            "name": "campus-only",
            "base_url": "https://ai-only.example.edu/v1",
            "api_key": "sk-only",
        },
        created_by=principal.user_id,
    )
    await db_session.flush()

    alias = await create_alias(
        db_session,
        payload={
            "alias_name": "chat_campus_unknown_fallback",
            "model_id": "campus-chat-model",
            "provider_id": primary["id"],
            "fallback_provider_names": ["does-not-exist"],
        },
        created_by=principal.user_id,
    )
    await db_session.commit()
    assert alias["fallback_provider_names"] == ["does-not-exist"]

    chains = await load_active_route_chains(db_session)

    assert chains["chat_campus_unknown_fallback"] == [
        ("campus-only", "https://ai-only.example.edu/v1", "campus-chat-model")
    ]


async def test_update_alias_can_change_fallback_chain(db_session) -> None:
    principal = await _university_admin(db_session)
    await settings_service.get_effective_settings(db_session, principal=principal)
    await provider_registry.ensure_defaults(db_session)

    primary = await create_provider(
        db_session,
        payload={
            "name": "campus-update-primary",
            "base_url": "https://ai-update.example.edu/v1",
            "api_key": "sk-update",
        },
        created_by=principal.user_id,
    )
    await db_session.flush()

    alias = await create_alias(
        db_session,
        payload={
            "alias_name": "chat_campus_update",
            "model_id": "campus-chat-model",
            "provider_id": primary["id"],
        },
        created_by=principal.user_id,
    )
    assert alias["fallback_provider_names"] == []

    updated = await update_alias(
        db_session,
        uuid.UUID(alias["id"]),
        payload={"fallback_provider_names": ["openrouter"]},
    )
    assert updated["fallback_provider_names"] == ["openrouter"]
    await db_session.commit()

    chains = await load_active_route_chains(db_session)
    assert [name for name, _, _ in chains["chat_campus_update"]] == [
        "campus-update-primary",
        "openrouter",
    ]


async def test_resolver_publishes_route_chains_into_snapshot(db_session) -> None:
    cfg = await resolver.resolve_and_publish(db_session)
    await db_session.commit()

    assert cfg.provider_route_chains["chat_cheap"] == [
        ("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat")
    ]
    # Every route must have a corresponding chain entry.
    assert set(cfg.provider_routes) <= set(cfg.provider_route_chains)

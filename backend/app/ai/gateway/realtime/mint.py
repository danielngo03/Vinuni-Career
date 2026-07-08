"""Mint a realtime session (Tier V2) — the single entry point.

Resolves the configured provider, binds the grounding system instruction + TTL
server-side, and returns a :class:`ConnectionDescriptor`. When realtime is
disabled or unconfigured, raises ``RealtimeUnavailableError`` so the caller falls
back to the browser-native voice tier. A PII-safe usage row is logged (alias
only) so realtime enters observability without leaking anything.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.realtime import config as realtime_config
from app.ai.gateway.realtime.providers import (
    ConnectionDescriptor,
    RealtimeUnavailableError,
    get_provider,
)
from app.ai.observability.usage import log_ai_usage_async
from app.ai.safety.input_guard import sanitize_instruction

_MINT_TASK_TYPE = "mock_interview_realtime"


async def mint_session(
    db: AsyncSession,
    *,
    system_instruction: str,
    locale: str,
    max_output_tokens: int,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> ConnectionDescriptor:
    """Mint an ephemeral realtime connection. Raises if disabled/unavailable."""

    cfg = realtime_config.current()
    if not cfg.enabled or not cfg.provider:
        raise RealtimeUnavailableError(
            details={"fallback": "voice", "reason": "REALTIME_DISABLED"}
        )

    # Defense-in-depth: scrub the instruction even though grounding already did.
    clean, _ = sanitize_instruction(system_instruction)
    provider = get_provider(cfg.provider)
    try:
        descriptor = await provider.mint_ephemeral(
            system_instruction=clean or system_instruction,
            locale=locale,
            ttl_seconds=cfg.ttl_seconds,
            max_output_tokens=max_output_tokens,
            provider_ref=cfg.provider,
            model=cfg.model,
            voice=cfg.voice,
        )
    except RealtimeUnavailableError:
        await log_ai_usage_async(
            db,
            task_type=_MINT_TASK_TYPE,
            alias=cfg.provider,
            success=False,
            user_id=user_id,
            session_id=session_id,
        )
        raise
    await log_ai_usage_async(
        db,
        task_type=_MINT_TASK_TYPE,
        alias=cfg.provider,
        success=True,
        user_id=user_id,
        session_id=session_id,
    )
    return descriptor

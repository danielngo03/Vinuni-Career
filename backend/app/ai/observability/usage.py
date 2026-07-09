"""PII-safe AI usage / cost tracking.

Mandatory per-request cost tracking (``docs/AI_PRODUCT_SPEC.md`` §5.4, §15;
``.claude/rules/ai.md``). Two layers:

1. ``log_ai_usage()`` — sync, always available, emits a structured log line
   with zero raw content. Used from sync contexts and tests.
2. ``log_ai_usage_async()`` — async, writes a DB row to ``ai_usage_log`` AND
   emits the same structured log line. Never raises: a DB failure degrades to
   the log-only path so the calling code path is never broken.

Neither function records raw prompt content, response content, PII, provider
name, real model name, API key, or IP address.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("ai.usage")


# --------------------------------------------------------------------------- #
# Bucket helpers                                                                #
# --------------------------------------------------------------------------- #


def _bucket(n: int) -> str:
    """Existing sync bucket labels — kept unchanged for backward compat."""
    if n <= 0:
        return "0"
    if n < 256:
        return "xs"
    if n < 1024:
        return "s"
    if n < 4096:
        return "m"
    if n < 16384:
        return "l"
    return "xl"


def _db_bucket(n: int) -> str:
    """DB char-length buckets per spec (0-500 / 500-2k / 2k-8k / 8k+)."""
    if n < 500:
        return "xs"
    if n < 2000:
        return "sm"
    if n < 8000:
        return "md"
    return "lg"


# --------------------------------------------------------------------------- #
# Sync logger (unchanged)                                                       #
# --------------------------------------------------------------------------- #


def log_ai_usage(
    *,
    task_type: str,
    alias: str,
    success: bool,
    prompt_chars: int = 0,
    completion_chars: int = 0,
) -> None:
    """Emit a metadata-only usage record. Never logs prompt/response content."""

    logger.info(
        "ai_usage",
        extra={
            "ai_task_type": task_type,
            "ai_model_alias": alias,  # internal alias only (never a provider/model name)
            "ai_success": success,
            "ai_prompt_bucket": _bucket(prompt_chars),
            "ai_completion_bucket": _bucket(completion_chars),
        },
    )


# --------------------------------------------------------------------------- #
# Async DB writer                                                               #
# --------------------------------------------------------------------------- #


async def log_ai_usage_async(
    db: AsyncSession,
    *,
    task_type: str,
    alias: str,
    success: bool,
    prompt_chars: int = 0,
    completion_chars: int = 0,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    cost_usd: float | None = None,
) -> None:
    """Insert a row into ``ai_usage_log`` and emit the structured log line.

    Never raises. A DB error downgrades to the sync log path so callers are
    never broken by an observability failure. The caller should NOT await this
    in the critical path of a response if latency matters — fire-and-forget via
    ``asyncio.create_task`` is preferred when the DB session outlives the call.

    Args:
        db: Active async SQLAlchemy session. The insert is flushed but the
            caller owns the surrounding transaction / commit.
        task_type: Logical task label, e.g. ``"ai_assistant_chat"``,
            ``"cv_bullets"``. No provider or model names.
        alias: Internal model alias only, e.g. ``"chat_cheap"``. Never a real
            provider model identifier.
        success: Whether the AI call completed without error.
        prompt_chars: Approximate character count of the prompt sent.
        completion_chars: Approximate character count of the completion received.
        user_id: Optional UUID of the authenticated user. ``None`` for
            anonymous or background/system calls.
        session_id: Optional UUID of the chat/AI session, if applicable.
        cost_usd: Optional estimated cost in USD. ``None`` when unavailable.
    """
    # Always emit the structured log line first (sync, cannot fail).
    log_ai_usage(
        task_type=task_type,
        alias=alias,
        success=success,
        prompt_chars=prompt_chars,
        completion_chars=completion_chars,
    )

    # Attempt the DB insert. If it fails for any reason, log a warning and
    # continue — observability must never break the product code path.
    nested = None
    try:
        from app.ai.observability.models import AiUsageLog  # local import avoids circular deps

        nested = await db.begin_nested()
        row = AiUsageLog(
            task_type=task_type,
            model_alias=alias,
            success=success,
            prompt_chars_bucket=_db_bucket(prompt_chars),
            completion_chars_bucket=_db_bucket(completion_chars),
            user_id=user_id,
            session_id=session_id,
            cost_usd=cost_usd,
        )
        db.add(row)
        await db.flush([row])
        await nested.commit()
    except Exception as exc:  # noqa: BLE001
        if nested is not None and nested.is_active:
            await nested.rollback()
        logger.warning(
            "ai_usage_log_db_write_failed",
            extra={
                "ai_task_type": task_type,
                "error": str(exc),
            },
        )

    # 1% online sampling to ai_eval_samples for async human review (§10.2).
    # Import is local to avoid circular deps; failure is silently absorbed.
    sample_nested = None
    try:
        from app.ai.observability.eval_samples import maybe_sample_async

        sample_nested = await db.begin_nested()
        await maybe_sample_async(
            db,
            task_type=task_type,
            alias=alias,
            success=success,
            prompt_chars=prompt_chars,
            completion_chars=completion_chars,
            user_id=user_id,
            session_id=session_id,
        )
        await sample_nested.commit()
    except Exception:  # noqa: BLE001
        if sample_nested is not None and sample_nested.is_active:
            await sample_nested.rollback()
        pass

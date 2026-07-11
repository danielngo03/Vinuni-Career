"""AI operational telemetry recorder.

Writes one ``AiOpsEvent`` row per call and upserts one ``AiUsageDaily``
row for the current UTC day grain (day × task_type × provider × model × org_id).

This function MUST NEVER raise — telemetry failure cannot be allowed to break
the AI call path.  Every code path is wrapped in a broad try/except that logs
a warning and swallows the exception.

Provider/model map to empty string ``""`` in the daily grain when None, so the
unique constraint never contains NULL values across databases.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.observability.models import AiOpsEvent, AiUsageDaily

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class OpsEventInput:
    """Plain data container for a single AI gateway call outcome.

    Populated by the AI gateway (Task 4) after each model call completes.
    Cost fields come from ``pricing.estimate_cost_usd_db`` (Task 1).
    """

    task_type: str
    alias: str
    provider: str | None
    model: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int | None
    status: str
    fallback_used: bool
    circuit_open: bool
    cost_usd: float | None
    unpriced: bool
    org_id: uuid.UUID | None
    user_id: uuid.UUID | None
    session_id: uuid.UUID | None
    request_id: str | None
    langfuse_trace_id: str | None


async def record_ops_event(
    session: AsyncSession,
    *,
    event: OpsEventInput,
) -> None:
    """Insert one ``AiOpsEvent`` and upsert one ``AiUsageDaily`` for today.

    Never raises — any exception is caught, logged at WARNING level, and
    swallowed so telemetry cannot disrupt the AI call path.

    The daily upsert is a read-modify-write within the caller's session
    (SQLite-safe; avoids PG-only ON CONFLICT syntax).  Two events with the
    same grain on the same day produce a single ``AiUsageDaily`` row with
    accumulated counters.
    """
    try:
        if event is None:
            return

        # --- 1. Append the raw per-call event row ---
        session.add(AiOpsEvent(**{k: getattr(event, k) for k in OpsEventInput.__slots__}))

        # --- 2. Upsert the daily rollup row ---
        day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        provider_key = event.provider or ""
        model_key = event.model or ""

        row = await session.scalar(
            select(AiUsageDaily).where(
                AiUsageDaily.day == day,
                AiUsageDaily.task_type == event.task_type,
                AiUsageDaily.provider == provider_key,
                AiUsageDaily.model == model_key,
                AiUsageDaily.org_id == event.org_id,
            )
        )

        if row is None:
            row = AiUsageDaily(
                day=day,
                task_type=event.task_type,
                provider=provider_key,
                model=model_key,
                org_id=event.org_id,
                requests=0,
                errors=0,
                fallbacks=0,
                blocked=0,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=0.0,
                latency_ms_sum=0,
                latency_ms_count=0,
            )
            session.add(row)

        row.requests += 1
        row.errors += 1 if event.status == "error" else 0
        row.fallbacks += 1 if event.fallback_used else 0
        row.blocked += 1 if event.status == "blocked" else 0
        row.prompt_tokens += event.prompt_tokens or 0
        row.completion_tokens += event.completion_tokens or 0
        row.cost_usd = float(row.cost_usd) + float(event.cost_usd or 0)  # Decimal from SQLite
        if event.latency_ms is not None:
            row.latency_ms_sum += event.latency_ms
            row.latency_ms_count += 1

        await session.flush()

    except Exception:  # telemetry must never break the AI call path
        _log.warning("ai_ops recorder failed", exc_info=True)

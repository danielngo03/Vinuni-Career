"""Billable AI usage ledger — the durable, idempotent charge-decision layer.

Source of truth for plan/package credit limits (``docs/PRODUCT_OPERATING_MODEL.md``
§3). Distinct from ``ai_usage_log`` (PII-safe provider call log) and
``ai_ops_event`` (superadmin ops telemetry): this ledger answers "who should be
charged how many credits for which feature, and was it charged".

Design contract:
- **Idempotent.** A caller-namespaced ``idempotency_key`` (globally unique when
  present) makes a Celery redelivery / client retry / cache reuse a no-op — it
  never double-charges. Build keys with :func:`make_idempotency_key`.
- **Charging rules (§3.2).** Credits are charged ONLY on a successful,
  user-visible result. ``blocked`` / ``provider_failed`` / ``validation_failed``
  / ``cached`` record the event with ``units_charged = 0`` (still useful for
  attribution + provider-cost accounting), but never bill the user.
- **No leakage.** Stores feature/task/scope/units/cost-estimate only — never
  provider/model names, prompts, tokens, or raw confidence.

This module is the FOUNDATION (B-579). Routing every AI call site through it
(B-580) and the persona credit-meter/upgrade UX (B-581) build on top; the
existing ``ai_settings.budget_guard`` (org USD budget) and
``ai_assistant.usage_service`` (per-user request throttle) remain the preflight
gates.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.observability.models import AiBillableUsage

# --------------------------------------------------------------------------- #
# Vocabulary                                                                   #
# --------------------------------------------------------------------------- #

# Billing scope — which budget the charge lands on.
SCOPE_USER = "user"
SCOPE_ORG = "org"
SCOPE_DEPARTMENT = "department"
SCOPE_PLATFORM = "platform"

# Acting persona.
PERSONA_STUDENT = "student"
PERSONA_PARTNER = "partner"
PERSONA_UNIVERSITY = "university"
PERSONA_SYSTEM = "system"

# Result status — drives the charging rule.
RESULT_SUCCESS = "success"
RESULT_PROVIDER_FAILED = "provider_failed"
RESULT_VALIDATION_FAILED = "validation_failed"
RESULT_CACHED = "cached"
RESULT_BLOCKED = "blocked"

# Only a successful, user-visible result bills the user (§3.2).
_CHARGEABLE = frozenset({RESULT_SUCCESS})

# Product feature keys (billable AI task taxonomy §3.3). Kept as constants so
# call sites don't drift on free-text values.
FEATURE_CHATBOT = "chatbot"
FEATURE_CV_EXTRACTION = "cv_extraction"
FEATURE_CV_SUGGESTION = "cv_suggestion"
FEATURE_CV_EDIT_COMMAND = "cv_edit_command"
FEATURE_CV_FIT_EXPLANATION = "cv_fit_explanation"
FEATURE_COVER_LETTER = "cover_letter"
FEATURE_INTERVIEW_SIM = "interview_sim"
FEATURE_LEARNING_PLAN = "learning_plan"
FEATURE_JD_EXTRACTION = "jd_extraction"
FEATURE_JD_WRITER = "jd_writer"
FEATURE_SCREENING_BRIEF = "screening_brief"
FEATURE_SCORECARD_SUGGESTION = "scorecard_suggestion"
FEATURE_EMBEDDINGS = "embeddings"
FEATURE_RERANK = "rerank"


def make_idempotency_key(feature_key: str, *parts: object) -> str:
    """Build a namespaced idempotency key: ``feature:part1:part2:…``.

    Callers pass the stable identity of the *result* (e.g. a
    ``(cv_version, job_version)`` pair, a suggestion id, or a chat message id) so
    the same logical result is only ever charged once.
    """

    return ":".join([feature_key, *(str(p) for p in parts)])


@dataclass(frozen=True, slots=True)
class UsageContext:
    """Everything the ledger needs to attribute + charge one AI call.

    ``idempotency_key`` is optional: omit it for genuinely one-off events (they
    always insert); provide it (via :func:`make_idempotency_key`) whenever the
    same logical result could be produced more than once and must be charged
    at most once.
    """

    actor_persona: str
    feature_key: str
    task_type: str
    billing_scope: str = SCOPE_PLATFORM
    actor_user_id: uuid.UUID | None = None
    org_id: uuid.UUID | None = None
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    idempotency_key: str | None = None


def units_for(result_status: str, base_units: int) -> int:
    """Apply the charging rule: bill ``base_units`` only on a chargeable result."""

    return base_units if result_status in _CHARGEABLE else 0


async def record_billable_usage(
    db: AsyncSession,
    *,
    ctx: UsageContext,
    result_status: str,
    base_units: int = 0,
    provider_cost_usd: float | None = None,
    ai_usage_log_id: uuid.UUID | None = None,
    ai_ops_event_id: uuid.UUID | None = None,
) -> AiBillableUsage:
    """Record one billable-usage row (idempotent on ``ctx.idempotency_key``).

    Returns the persisted (or pre-existing) row. The row is flushed so its ``id``
    is populated; the caller owns the surrounding transaction / commit — matching
    every other write service in this codebase.

    Idempotency: when ``ctx.idempotency_key`` is set and a row already exists for
    it, the existing row is returned unchanged (no second charge). A concurrent
    insert that loses the unique-constraint race is resolved the same way.
    """

    if ctx.idempotency_key is not None:
        existing = await _by_idempotency_key(db, ctx.idempotency_key)
        if existing is not None:
            return existing

    row = AiBillableUsage(
        actor_user_id=ctx.actor_user_id,
        actor_persona=ctx.actor_persona,
        org_id=ctx.org_id,
        billing_scope=ctx.billing_scope,
        feature_key=ctx.feature_key,
        task_type=ctx.task_type,
        resource_type=ctx.resource_type,
        resource_id=ctx.resource_id,
        session_id=ctx.session_id,
        idempotency_key=ctx.idempotency_key,
        units_charged=units_for(result_status, base_units),
        provider_cost_usd=provider_cost_usd,
        result_status=result_status,
        ai_usage_log_id=ai_usage_log_id,
        ai_ops_event_id=ai_ops_event_id,
    )
    # Savepoint so a duplicate-key race (or any flush error) never poisons the
    # caller's transaction — the caller may be running this best-effort (the AI
    # runner) and must keep a usable session either way.
    nested = await db.begin_nested()
    db.add(row)
    try:
        await db.flush([row])
        await nested.commit()
        return row
    except IntegrityError:
        if nested.is_active:
            await nested.rollback()
        db.expunge(row)
        # Lost the idempotency race — return the row the winner inserted.
        if ctx.idempotency_key is not None:
            existing = await _by_idempotency_key(db, ctx.idempotency_key)
            if existing is not None:
                return existing
        raise
    except Exception:
        if nested.is_active:
            await nested.rollback()
        db.expunge(row)
        raise


async def _by_idempotency_key(db: AsyncSession, key: str) -> AiBillableUsage | None:
    return (
        await db.execute(select(AiBillableUsage).where(AiBillableUsage.idempotency_key == key))
    ).scalar_one_or_none()


async def billable_summary(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    since: datetime,
) -> dict:
    """Credits charged to a user since ``since``, total + per-feature.

    Powers the student credit meter (B-581). Counts only ``units_charged`` — free
    / blocked / failed rows contribute 0, so this reflects real billed usage.
    """

    rows = (
        await db.execute(
            select(
                AiBillableUsage.feature_key,
                func.coalesce(func.sum(AiBillableUsage.units_charged), 0),
            )
            .where(
                AiBillableUsage.actor_user_id == actor_user_id,
                AiBillableUsage.created_at >= since,
            )
            .group_by(AiBillableUsage.feature_key)
        )
    ).all()

    by_feature = {feature: int(units) for feature, units in rows}
    return {
        "total_units": sum(by_feature.values()),
        "by_feature": by_feature,
        "since": since.isoformat(),
    }

"""Meter CV ingestion against the uploader's AI energy — PAID tiers only.

The CV ingestion cascade is cost-tiered (``docs/CV_INGESTION_EXTRACTION_SPEC.md``
§3): native text (free) → local OCR (free) → a cheap vision-LLM (paid) → optional
text-LLM structuring (paid). Only the PAID tiers spend provider tokens, so only
those are charged — and only when they actually produced a validated, user-visible
result (charge-on-success, ``docs/AI_PRODUCT_SPEC.md`` §3.2).

Design (mirrors ``opportunities.jd_upload_service._meter_extraction``):

- **Preflight** the weekly-energy hard gate BEFORE running the cascade. On
  exhaustion we do NOT raise — the upload still succeeds and the cascade runs
  offline-only (native text stays free, no fabrication); a document that needs a
  paid tier surfaces a user-safe ``ai_unavailable`` state instead of a 500.
- **Charge** ``FEATURE_CV_EXTRACTION`` (cost-weighted, vision ≫ text) when the
  vision-LLM or text-LLM tier produced the result; native-text/OCR-only extractions
  record nothing. A vision call that was ATTEMPTED but yielded no user-visible
  output records a ``provider_failed`` (0-credit) row for superadmin cost
  visibility — the student is never charged for a failed output.
- **Idempotent** on the ingestion / parse-run id: a Celery redelivery or retry of
  the same extraction never double-charges.

Governance: the vision tier still issues its own downscaled-image HTTP call inside
``app/ai/extraction/adapters/vision.py`` (already gated on ``real_provider_active``);
routing that multimodal call fully through the gateway provider is a tracked
follow-up (WS-2). This module closes the METERING half of that leak now.

Everything here is best-effort: an accounting fault must never break a CV upload.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.energy.constants import FEATURE_CV_EXTRACTION
from app.ai.energy.service import build_usage_context, charge_units, enforce_energy
from app.ai.extraction.adapters import EnginePolicy
from app.ai.extraction.cv_ingestion_cascade import IngestionOutcome
from app.ai.observability.billable_usage import record_billable_usage
from app.ai.observability.usage import log_ai_usage_async
from app.shared.exceptions import QuotaExceededError
from app.shared.permissions import Principal

logger = logging.getLogger(__name__)

_TASK_TYPE = "cv_extraction"
_ALIAS = "cv_extraction"  # internal alias only — never a provider/model name


async def preflight_gate(session: AsyncSession, *, principal: Principal) -> bool:
    """Return ``True`` when the PAID extraction tiers must be withheld.

    Runs the weekly-energy hard gate. On exhaustion the caller should run the
    cascade with :func:`gated_policy` (paid tiers off) so free native-text
    extraction still works and a scan surfaces ``ai_unavailable`` — never a 500,
    never a fabricated CV. Degrades OPEN on any infra fault: a metering failure
    must never block an upload.
    """

    if not principal.is_authenticated:
        return False
    try:
        await enforce_energy(session, principal=principal)
        return False
    except QuotaExceededError:
        return True
    except Exception:  # noqa: BLE001 — never block an upload on a metering fault
        logger.warning("cv_extraction_preflight_failed", exc_info=True)
        return False


def gated_policy(policy: EnginePolicy) -> EnginePolicy:
    """A copy of ``policy`` with the PAID (vision + text-LLM) tiers disabled."""

    return replace(policy, vision_enabled=False, llm_enabled=False)


async def charge_extraction(
    session: AsyncSession,
    principal: Principal | None,
    outcome: IngestionOutcome,
    *,
    resource_type: str,
    resource_id: uuid.UUID,
) -> None:
    """Record the billable-usage row for one extraction (paid tiers only).

    - vision/text-LLM produced the result → charge ``FEATURE_CV_EXTRACTION``
      (``success``), idempotent on ``resource_id``.
    - vision attempted but produced nothing → ``provider_failed`` (0 credits) so
      the real provider cost is attributable, but the student is not charged.
    - native-text / local-OCR only, gated, or a hard reject → nothing recorded.
    """

    if principal is None or not principal.is_authenticated:
        return

    idempotency_parts: tuple[object, ...] | None
    if outcome.vision_used or outcome.llm_used:
        result_status = "success"
        units = charge_units(FEATURE_CV_EXTRACTION)
        idempotency_parts = (resource_id,)
    elif outcome.vision_attempted:
        # A real paid call happened but yielded no user-visible CV — attribute the
        # cost, charge nothing. No idempotency key: each real attempt is its own
        # cost event, and it must never collide with the eventual success charge.
        result_status = "provider_failed"
        units = 0
        idempotency_parts = None
    else:
        return  # free tier / withheld / rejected — no tokens spent

    try:
        ctx = build_usage_context(
            principal,
            feature_key=FEATURE_CV_EXTRACTION,
            task_type=_TASK_TYPE,
            resource_type=resource_type,
            resource_id=resource_id,
            idempotency_parts=idempotency_parts,
        )
        await record_billable_usage(
            session, ctx=ctx, result_status=result_status, base_units=units
        )
        await log_ai_usage_async(
            session,
            task_type=_TASK_TYPE,
            alias=_ALIAS,
            success=result_status == "success",
            user_id=principal.user_id,
        )
    except Exception:  # noqa: BLE001 — accounting must never break the extraction
        logger.warning("cv_extraction_metering_failed", exc_info=True)


__all__ = ["preflight_gate", "gated_policy", "charge_extraction"]

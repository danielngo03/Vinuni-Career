"""On-demand fraud scan for a job posting (AI_PRODUCT_SPEC §3 fraud_detection).

Collects deterministic signals from real platform data through the owning
modules' application facades (``job_read_facade.fraud_scan_snapshot``,
``org_reporting_facade.trust_snapshot_for`` — no cross-module ORM imports)
and scores them with the pure rule engine ``app.ai.safety.fraud_detection``.
High-risk assessments (``risk_score >= 0.85``, §9.3) are escalated to
``human_review_queue``.

ADVISORY ONLY: the response is university-moderator-facing and reports
``risk_level`` wording + reason codes — never the raw internal ``risk_score``
(the queue's ``findings_json`` keeps it internally for the moderator audit
trail, which is a staff surface, not an end-user surface).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.safety.content_moderation import check_content
from app.ai.safety.fraud_detection import FraudAssessment, assess_fraud_signals
from app.modules.moderation.application import review_queue_service
from app.modules.opportunities.application import job_read_facade
from app.modules.organization.application import org_reporting_facade
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal


async def _collect_signals(session: AsyncSession, job_snapshot: dict) -> dict:
    trust = await org_reporting_facade.trust_snapshot_for(
        session, job_snapshot["org_id"]
    )

    org_age_days: float | None = None
    has_verified = None
    if trust is not None:
        created = trust["created_at"]
        if created.tzinfo is None:  # SQLite test backend stores naive datetimes
            created = created.replace(tzinfo=UTC)
        org_age_days = (datetime.now(UTC) - created).total_seconds() / 86400
        has_verified = trust["is_verified"]

    content = check_content(job_snapshot["text"])
    categories = {f.category for f in content.findings}

    return {
        "org_age_days": org_age_days,
        "has_verified_email_domain": has_verified,
        "jobs_posted_last_7d": job_snapshot["org_jobs_last_7d"],
        "fee_collection_flagged": "fee_collection" in categories,
        "external_contact_in_content": "off_platform_contact" in categories,
    }


async def scan_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
) -> dict:
    """Run a fraud-signal scan on one job (university moderator action).

    Returns a moderator-safe summary and escalates to the human review queue
    when the §9.3 threshold is met. Idempotent: repeat scans refresh the same
    PENDING queue item instead of duplicating it.
    """
    await review_queue_service._require_university(session, principal)

    snapshot = await job_read_facade.fraud_scan_snapshot(session, job_id)
    if snapshot is None:
        raise ResourceNotFoundError()

    signals = await _collect_signals(session, snapshot)
    assessment: FraudAssessment = assess_fraud_signals(signals)

    escalated = False
    if assessment.requires_human_review:
        await review_queue_service.enqueue(
            session,
            source=review_queue_service.SOURCE_FRAUD,
            resource_type="job",
            resource_id=snapshot["id"],
            org_id=snapshot["org_id"],
            severity="high",
            findings=assessment.as_dict(),
        )
        escalated = True

    return {
        "job_id": str(snapshot["id"]),
        "risk_level": assessment.risk_level,
        "requires_human_review": assessment.requires_human_review,
        "escalated": escalated,
        "signals": [
            {"code": s.code, "reason": s.reason} for s in assessment.signals
        ],
    }

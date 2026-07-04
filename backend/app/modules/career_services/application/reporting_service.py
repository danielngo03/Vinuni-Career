"""Counselor outcomes reporting read model (B-554).

RBAC resource: ``career_services_reporting`` (``read``). Aggregates the
counselor workspace's own tables (cohorts, at-risk flags, CV review queue,
appointments, interventions) into counts a counselor/university-admin can act
on. This is a same-module aggregation (no cross-module outbox/materializer is
needed — unlike ``career_outcomes``, which consumes an event from
``recruitment``): every source table here is already owned by this module, so
the read service queries them directly, mirroring the read-model shape of
``career_outcomes.application.read_service`` (aggregates + friendly labels,
never raw enum codes alone).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.career_services.application.common import require_org
from app.modules.career_services.domain import catalog
from app.modules.career_services.domain.models import (
    Appointment,
    AtRiskFlag,
    Cohort,
    CvReviewQueueItem,
    InterventionRecord,
)
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "career_services_reporting"


async def _counts_by(
    session: AsyncSession, column, *, org_id: uuid.UUID, model
) -> dict[str, int]:
    rows = (
        await session.execute(
            select(column, func.count())
            .where(model.org_id == org_id)
            .group_by(column)
        )
    ).all()
    return {str(k): int(n) for k, n in rows}


async def get_reporting_summary(
    session: AsyncSession,
    *,
    principal: Principal,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=org_id)

    active_cohorts = (
        await session.execute(
            select(func.count()).select_from(Cohort).where(
                Cohort.org_id == org_id,
                Cohort.deleted_at.is_(None),
                Cohort.status == catalog.COHORT_ACTIVE,
            )
        )
    ).scalar_one()

    risk_by_status_raw = await _counts_by(
        session, AtRiskFlag.status, org_id=org_id, model=AtRiskFlag
    )
    risk_by_severity_raw = await _counts_by(
        session, AtRiskFlag.severity, org_id=org_id, model=AtRiskFlag
    )
    cv_review_by_status_raw = await _counts_by(
        session, CvReviewQueueItem.status, org_id=org_id, model=CvReviewQueueItem
    )
    appt_by_status_raw = await _counts_by(
        session, Appointment.status, org_id=org_id, model=Appointment
    )
    intervention_by_outcome_raw = await _counts_by(
        session, InterventionRecord.outcome, org_id=org_id, model=InterventionRecord
    )

    open_at_risk = sum(
        n for code, n in risk_by_status_raw.items() if code in catalog.RISK_OPEN_STATUSES
    )
    open_cv_reviews = sum(
        n
        for code, n in cv_review_by_status_raw.items()
        if code in catalog.CV_REVIEW_OPEN_STATUSES
    )

    def _labelled(raw: dict[str, int], label_fn) -> list[dict]:
        return [
            {"code": code, "label": label_fn(code, locale=locale), "count": n}
            for code, n in sorted(raw.items())
        ]

    return {
        "active_cohorts": int(active_cohorts),
        "open_at_risk_flags": int(open_at_risk),
        "open_cv_reviews": int(open_cv_reviews),
        "at_risk_by_status": _labelled(risk_by_status_raw, catalog.risk_status_label),
        "at_risk_by_severity": _labelled(
            risk_by_severity_raw, catalog.risk_severity_label
        ),
        "cv_review_by_status": _labelled(
            cv_review_by_status_raw, catalog.cv_review_status_label
        ),
        "appointments_by_status": _labelled(
            appt_by_status_raw, catalog.appointment_status_label
        ),
        "interventions_by_outcome": _labelled(
            intervention_by_outcome_raw, catalog.intervention_outcome_label
        ),
    }

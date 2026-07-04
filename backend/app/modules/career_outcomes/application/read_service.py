"""University-scoped read API for materialized career outcomes.

The ``career_outcome_records`` table holds NO student PII and NO salary (see
:mod:`app.modules.career_outcomes.domain.models`), so this surface exposes
aggregate KPIs and a privacy-safe record list (position title, employer name,
start date, friendly trust/outcome labels). RBAC is university-only — mirrors
``dashboards.university_dashboard._require_university`` — so partners/students
cannot read cross-employer outcome reporting.

Employer display names are resolved through the ``organization`` reporting facade
(no cross-module ORM import). Raw enum codes never reach the response; they are
mapped to bilingual labels in :mod:`..domain.labels`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.career_outcomes.domain import labels
from app.modules.career_outcomes.domain.models import CareerOutcomeRecord
from app.modules.organization.application import org_reporting_facade
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.pagination import clamp_limit
from app.shared.permissions import Principal, permission_checker

_TOP_EMPLOYERS = 8
_RECENT = 8


async def _require_university(session: AsyncSession, principal: Principal) -> None:
    """University-staff / superadmin only (mirrors the dashboard gate)."""

    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.is_superadmin:
        return
    if not permission_checker.can(principal, "jobs", "moderate"):
        raise PermissionDeniedError(details={"reason": "university_only"})
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "university_only"})


# --------------------------------------------------------------------------- #
# Internal counters (also used by tests; no RBAC)                             #
# --------------------------------------------------------------------------- #


async def count_outcomes(
    session: AsyncSession,
    *,
    employer_org_id: uuid.UUID | None = None,
    trust_level: int | None = None,
) -> int:
    """Count materialized outcomes, optionally scoped by employer/trust level."""

    stmt = select(func.count()).select_from(CareerOutcomeRecord)
    if employer_org_id is not None:
        stmt = stmt.where(CareerOutcomeRecord.employer_org_id == employer_org_id)
    if trust_level is not None:
        stmt = stmt.where(CareerOutcomeRecord.trust_level == trust_level)
    return (await session.execute(stmt)).scalar_one()


async def list_outcomes(
    session: AsyncSession,
    *,
    employer_org_id: uuid.UUID | None = None,
    trust_level: int | None = None,
    limit: int = 50,
) -> Sequence[CareerOutcomeRecord]:
    """List recent materialized outcomes (most recent first)."""

    stmt = select(CareerOutcomeRecord).order_by(
        CareerOutcomeRecord.recorded_at.desc(), CareerOutcomeRecord.id.desc()
    )
    if employer_org_id is not None:
        stmt = stmt.where(CareerOutcomeRecord.employer_org_id == employer_org_id)
    if trust_level is not None:
        stmt = stmt.where(CareerOutcomeRecord.trust_level == trust_level)
    stmt = stmt.limit(max(limit, 0))
    return list((await session.execute(stmt)).scalars().all())


# --------------------------------------------------------------------------- #
# University read API (RBAC'd, label-mapped, PII-free)                        #
# --------------------------------------------------------------------------- #


def _record_payload(
    rec: CareerOutcomeRecord, *, employer_name: str, locale: str
) -> dict:
    return {
        "id": str(rec.id),
        "position_title": rec.position_title,
        "employer_name": employer_name,
        "start_date": rec.start_date.isoformat() if rec.start_date else None,
        "outcome": labels.outcome_label(rec.outcome_type, locale=locale),
        "trust_label": labels.trust_label(rec.trust_level, locale=locale),
        "recorded_at": rec.recorded_at.isoformat() if rec.recorded_at else None,
    }


async def get_kpi(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    """University KPI roll-up: totals, trust-level mix, top employers, recents."""

    await _require_university(session, principal)

    total = await count_outcomes(session)

    trust_rows = (
        await session.execute(
            select(
                CareerOutcomeRecord.trust_level,
                func.count().label("n"),
            ).group_by(CareerOutcomeRecord.trust_level)
        )
    ).all()
    by_trust_level = [
        {
            "trust_level": int(r.trust_level),
            "label": labels.trust_label(int(r.trust_level), locale=locale),
            "count": int(r.n),
        }
        for r in sorted(trust_rows, key=lambda r: int(r.trust_level))
    ]

    emp_rows = (
        await session.execute(
            select(
                CareerOutcomeRecord.employer_org_id,
                func.count().label("n"),
            )
            .group_by(CareerOutcomeRecord.employer_org_id)
            .order_by(func.count().desc())
            .limit(_TOP_EMPLOYERS)
        )
    ).all()
    names = await org_reporting_facade.display_names_for(
        session, [r.employer_org_id for r in emp_rows]
    )
    top_employers = [
        {
            "employer_name": names.get(r.employer_org_id, "VinUni Career"),
            "count": int(r.n),
        }
        for r in emp_rows
    ]

    recent_rows = await list_outcomes(session, limit=_RECENT)
    recent_names = await org_reporting_facade.display_names_for(
        session, [r.employer_org_id for r in recent_rows]
    )
    recent = [
        _record_payload(
            r,
            employer_name=recent_names.get(r.employer_org_id, "VinUni Career"),
            locale=locale,
        )
        for r in recent_rows
    ]

    return {
        "total_outcomes": int(total),
        "by_trust_level": by_trust_level,
        "top_employers": top_employers,
        "recent": recent,
    }


async def list_records(
    session: AsyncSession,
    *,
    principal: Principal,
    trust_level: int | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> dict:
    """University paginated (limit-only) privacy-safe outcome record list."""

    await _require_university(session, principal)
    page_limit = clamp_limit(limit)
    rows = await list_outcomes(
        session, trust_level=trust_level, limit=page_limit
    )
    names = await org_reporting_facade.display_names_for(
        session, [r.employer_org_id for r in rows]
    )
    items = [
        _record_payload(
            r,
            employer_name=names.get(r.employer_org_id, "VinUni Career"),
            locale=locale,
        )
        for r in rows
    ]
    return {"items": items, "count": len(items)}

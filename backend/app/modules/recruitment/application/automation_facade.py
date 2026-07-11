"""Recruitment read/write seam for the workflow automation engine.

The visual workflow builder's recruiting-automation nodes
(``ai_screen_application`` / ``auto_advance_on_gate`` / ``notify``) need a small,
leak-safe surface into the recruitment module WITHOUT the ``workflow`` module
reaching into ``recruitment.domain.models`` (forbidden by the module-boundary
guard). This facade is that surface: it owns the ``Application`` ORM and returns
only ids / coarse status, and it drives a stage advance through the SAME manual
advance path a partner uses — so an automated move can never do anything a human
partner could not (identical RBAC, identical gate, identical audit/notify).

Nothing here bypasses a stage gate: :func:`auto_advance_if_gate_met` reuses
``stage_service.advance_application_stage`` and maps its precise gate/transition
errors to a NO-WRITE "held" outcome instead of forcing the move.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.organization.application import org_reporting_facade
from app.modules.recruitment.application import scorecard_service, stage_service
from app.modules.recruitment.application.errors import (
    IllegalApplicationTransitionError,
    ScoreBelowThresholdError,
    ScorecardRequiredError,
)
from app.modules.recruitment.domain import lifecycle, pipeline
from app.modules.recruitment.domain.models import Application, CandidateStage, PipelineStage
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal


async def application_screening_ref(
    session: AsyncSession, *, application_id: uuid.UUID
) -> dict | None:
    """Leak-safe ref an automation node needs to screen an application, or ``None``.

    Returns only ids + coarse status: ``{snapshot_id, job_id, org_id, status}``.
    Never the applicant identity, CV text, or contact details.
    """

    app = (
        await session.execute(
            select(Application).where(
                Application.id == application_id, Application.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if app is None or app.snapshot_id is None:
        return None
    return {
        "snapshot_id": app.snapshot_id,
        "job_id": app.job_id,
        "org_id": app.org_id,
        "status": app.status,
    }


async def resolve_assignee_user_id(
    session: AsyncSession, *, application_id: uuid.UUID
) -> uuid.UUID | None:
    """The user_id of the recruiter this application is assigned to, or ``None``.

    Resolved through the org read facade (never imports the ``Membership`` ORM).
    ``None`` when the application is unassigned or the membership no longer resolves.
    """

    app = (
        await session.execute(
            select(Application).where(
                Application.id == application_id, Application.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if app is None or app.assigned_to_membership_id is None:
        return None
    brief = await org_reporting_facade.member_brief(
        session, org_id=app.org_id, membership_id=app.assigned_to_membership_id
    )
    return brief.user_id if brief is not None else None


async def evaluate_stage_gate(session: AsyncSession, *, application_id: uuid.UUID) -> dict:
    """Read-only: is the current stage's advance gate met? NEVER writes.

    Returns ``{applicable, gate_met, reason, from_stage, next_stage}``. Used by the
    dry-run path so a simulation can report what an ``auto_advance_on_gate`` node
    WOULD do without moving the candidate.
    """

    app = (
        await session.execute(
            select(Application).where(
                Application.id == application_id, Application.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if app is None or app.status != lifecycle.UNDER_REVIEW:
        return {"applicable": False, "gate_met": False, "reason": "not_applicable"}

    active = (
        await session.execute(
            select(CandidateStage).where(
                CandidateStage.application_id == app.id,
                CandidateStage.status == pipeline.STAGE_ACTIVE,
            )
        )
    ).scalars().first()
    if active is None:
        # No stage row yet -> the first advance is pipeline ENTRY (no prior gate).
        return {
            "applicable": True,
            "gate_met": True,
            "reason": "pipeline_entry",
            "next_stage": None,
        }

    stage = (
        await session.execute(select(PipelineStage).where(PipelineStage.id == active.stage_id))
    ).scalar_one_or_none()
    if stage is None:
        return {"applicable": False, "gate_met": False, "reason": "not_applicable"}

    gate = await scorecard_service.evaluate_advance_gate(
        session, application_id=app.id, stage=stage
    )
    return {
        "applicable": True,
        "gate_met": gate.allowed,
        "reason": None if gate.allowed else (gate.reason or "gate_not_met"),
        "from_stage": stage.name,
    }


async def auto_advance_if_gate_met(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    ctx: RequestContext,
    idempotency_key: str | None,
    locale: str = "vi",
) -> dict:
    """Advance the candidate to the next stage ONLY if the gate is already met.

    Reuses ``stage_service.advance_application_stage`` (the manual partner path):
    same RBAC (``applications:read``), same ``required_action`` gate, same audit +
    neutral student notification. The gate is NEVER bypassed — a not-met gate
    raises inside the advance BEFORE any mutation, and we translate that into a
    no-write ``{"advanced": False, "reason": "gate_not_met"}``. ``emit_trigger`` is
    forced off so an automated move cannot re-fire the ``stage_changed`` trigger
    and cascade into itself.

    Returns ``{advanced: bool, reason: str | None}``.
    """

    try:
        await stage_service.advance_application_stage(
            session,
            principal=principal,
            application_id=application_id,
            idempotency_key=idempotency_key,
            ctx=ctx,
            locale=locale,
            emit_trigger=False,
        )
    except (ScorecardRequiredError, ScoreBelowThresholdError):
        return {"advanced": False, "reason": "gate_not_met"}
    except IllegalApplicationTransitionError:
        return {"advanced": False, "reason": "not_applicable"}
    except ResourceNotFoundError:
        return {"advanced": False, "reason": "not_found"}
    return {"advanced": True, "reason": None}

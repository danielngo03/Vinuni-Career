"""HTTP surface for the workforce pattern — the one real consumer wired end to
end (bulk screening-brief generation for a partner reviewing many applicants).

Endpoints:
  POST /ai/workforce/screening-briefs        Start a bulk screening-brief run
  POST /ai/workforce/operations-analysis     Start a university ops deep-analysis
  GET  /ai/workforce/runs/{run_id}            Poll run status + results (both)

Deviation from ``docs/AI_PRODUCT_SPEC.md`` §4.2's illustrative
``GET /api/v1/ai/jobs/{job_id}`` path: this codebase already uses `/jobs` for
job postings (``opportunities``), so ``/ai/workforce/runs/{run_id}`` is used
instead to avoid path collision/ambiguity. Documented here per that section's
own precedent of noting implementation deviations from the aspirational shape.

Permission: partner persona with ``applications:read`` on the job's org (same
gate ``apply_service.list_job_applications`` already enforces for the
single-application screening-brief endpoint). Advisory only — no tool
confirmation is required because nothing is mutated; this only reads
applications and generates advisory bullets, exactly like the existing
single-application ``ai-screening-brief`` route.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import workforce
from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.shared.responses import success

router = APIRouter(prefix="/ai/workforce", tags=["ai-workforce"])


class StartBulkScreeningBriefBody(BaseModel):
    job_id: uuid.UUID


class StartOperationsAnalysisBody(BaseModel):
    target_org_id: uuid.UUID
    target_type: str = "partner_hiring_quality"


@router.post(
    "/screening-briefs",
    summary="Start a bulk AI screening-brief run for every (capped) applicant on a job",
)
async def start_bulk_screening_briefs(
    body: StartBulkScreeningBriefBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Fan out advisory screening briefs across a job's applicants.

    Returns ``{ data: { run_id, status, total_subtasks } }`` immediately; the
    caller polls ``GET /ai/workforce/runs/{run_id}`` for progress/results.
    Advisory only — the recruiter makes every hire/reject decision.
    """
    data = await workforce.start_bulk_screening_brief_run(
        session, principal=auth.principal, job_id=body.job_id
    )
    return success(data)


@router.post(
    "/operations-analysis",
    summary="Start a university operations deep-analysis run on a partner target",
)
async def start_operations_analysis(
    body: StartOperationsAnalysisBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Fan out a bounded, READ-ONLY multi-agent analysis of a partner's hiring
    quality, then synthesize a privacy-safe report.

    Returns ``{ data: { run_id, status, total_subtasks, target_type } }``
    immediately; poll ``GET /ai/workforce/runs/{run_id}`` for the report. RBAC:
    a university-org staffer holding ``partners:read`` (or superadmin). Advisory
    only — no consequential domain write.
    """
    data = await workforce.start_operations_analysis_run(
        session,
        principal=auth.principal,
        target_org_id=body.target_org_id,
        target_type=body.target_type,
    )
    return success(data)


@router.get(
    "/runs/{run_id}",
    summary="Poll a workforce run's status and (once terminal) aggregated results",
)
async def get_workforce_run(
    run_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await workforce.get_workforce_run_status(
        session, principal=auth.principal, run_id=run_id
    )
    return success(data)

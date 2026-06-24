"""
AI Operations module — AI run lifecycle, SSE progress streaming.

Endpoints:
  POST /ai/runs                 → create run record, enqueue, return {run_id} < 300ms
  GET  /ai/runs/{id}            → run status + result
  GET  /ai/runs/{id}/stream     → SSE: real-time progress events
  POST /ai/runs/{id}/cancel     → cancel a running run
  GET  /ai/runs/                → list caller's runs
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.agents import WORKFORCE_VERSION, describe_workforce
from app.modules.access.api.auth import get_current_user
from app.modules.access.api.identity import get_active_identity
from app.platform.database.models import User, UserOrgRole
from app.platform.database.models.ai_runs import AIRun, AIRunEvent
from app.platform.database.session import SessionLocal, get_db
from app.platform.workflows import get_workflow_dispatcher
from app.shared.ids import new_id

router = APIRouter(prefix="/ai/runs", tags=["ai-runs"])

class AIRunType(StrEnum):
    CV_EXTRACTION = "cv_extraction"
    PROFILE_MATCHING = "profile_matching"
    JD_ANALYSIS = "jd_analysis"
    MODERATION = "moderation"
    ADMIN_REVIEW = "admin_review"
    VERIFICATION = "verification"
    CAREER_COACHING = "career_coaching"


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class CreateRunRequest(BaseModel):
    run_type: AIRunType = Field(..., description="Specialist AI task to execute")
    input_ref: str | None = Field(None, description="Reference to input object, e.g. 'cv:{id}'")
    run_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Task inputs. Raw PII should be minimized and is never returned in event traces.",
    )

    @field_validator("run_metadata")
    @classmethod
    def limit_metadata_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, default=str).encode()
        if len(encoded) > 250_000:
            raise ValueError("run_metadata must be at most 250 KB")
        return value


class RunResponse(BaseModel):
    run_id: str
    run_type: str
    status: str
    org_id: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result: dict | None = None
    error: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class AgentCapabilityResponse(BaseModel):
    task_type: str
    agent: str
    purpose: str
    human_review_policy: str
    workforce_version: str = WORKFORCE_VERSION


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=RunResponse, status_code=202, include_in_schema=False)
@router.post("/", response_model=RunResponse, status_code=202)
def create_run(
    body: CreateRunRequest,
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunResponse:
    """Create an AI run record and enqueue execution. Returns run_id in < 300ms."""
    run = AIRun(
        id=new_id(),
        run_type=body.run_type.value,
        status="QUEUED",
        org_id=identity.org_id,
        user_id=current_user.id,
        input_ref=body.input_ref,
        run_metadata=body.run_metadata,
        input_hash=_input_hash(body.run_type.value, body.input_ref, body.run_metadata),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        get_workflow_dispatcher().dispatch_ai_run(run.id)
    except Exception as exc:
        run.status = "FAILED"
        run.error = f"Workflow dispatch failed: {exc}"[:1000]
        run.finished_at = datetime.now(UTC)
        db.commit()
        raise

    return _run_response(run)


@router.get("/capabilities", response_model=list[AgentCapabilityResponse])
def agent_capabilities() -> list[AgentCapabilityResponse]:
    return [AgentCapabilityResponse(**item) for item in describe_workforce()]


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: str,
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunResponse:
    run = _get_run_or_404(db, run_id, current_user.id, identity.org_id)
    return _run_response(run)


@router.get("/{run_id}/stream")
async def stream_run(
    run_id: str,
    request: Request,
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Server-Sent Events stream for real-time AI run progress."""
    _get_run_or_404(db, run_id, current_user.id, identity.org_id)

    async def event_generator() -> AsyncGenerator[str]:
        last_seq = -1
        max_polls = 300  # max 5 minutes at 1-second poll
        polls = 0
        while polls < max_polls:
            if await request.is_disconnected():
                break
            with SessionLocal() as session:
                run = session.get(AIRun, run_id)
                if run:
                    # Emit new events since last seen
                    new_events = session.scalars(
                        select(AIRunEvent)
                        .where(
                            AIRunEvent.run_id == run_id,
                            AIRunEvent.sequence > last_seq,
                        )
                        .order_by(AIRunEvent.sequence)
                    ).all()
                    for evt in new_events:
                        last_seq = evt.sequence
                        data = json.dumps({
                            "sequence": evt.sequence,
                            "event_type": evt.event_type,
                            "payload": evt.payload,
                            "occurred_at": evt.occurred_at.isoformat(),
                        })
                        yield f"data: {data}\n\n"

                    # Emit run status heartbeat
                    yield f"data: {json.dumps({'run_status': run.status, 'sequence': last_seq})}\n\n"

                    if run.status in {"DONE", "FAILED", "CANCELLED"}:
                        yield f"data: {json.dumps({'event_type': 'stream_end', 'status': run.status})}\n\n"
                        break

            polls += 1
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{run_id}/cancel", response_model=RunResponse)
def cancel_run(
    run_id: str,
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunResponse:
    run = _get_run_or_404(db, run_id, current_user.id, identity.org_id)
    if run.status in {"QUEUED", "RUNNING"}:
        run.status = "CANCELLED"
        run.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(run)
    return _run_response(run)


@router.get("", response_model=list[RunResponse], include_in_schema=False)
@router.get("/", response_model=list[RunResponse])
def list_runs(
    run_type: str | None = None,
    status: str | None = None,
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RunResponse]:
    stmt = (
        select(AIRun)
        .where(
            AIRun.user_id == current_user.id,
            AIRun.org_id == identity.org_id,
        )
        .order_by(AIRun.created_at.desc())
        .limit(50)
    )
    if run_type:
        stmt = stmt.where(AIRun.run_type == run_type)
    if status:
        stmt = stmt.where(AIRun.status == status)
    runs = db.scalars(stmt).all()
    return [_run_response(r) for r in runs]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_run_or_404(
    db: Session,
    run_id: str,
    user_id: str,
    org_id: str,
) -> AIRun:
    from app.shared.errors import AppError, ErrorCode

    run = db.get(AIRun, run_id)
    if not run or run.user_id != user_id or run.org_id != org_id:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="AI run not found",
            status_code=404,
        )
    return run


def _run_response(run: AIRun) -> RunResponse:
    return RunResponse(
        run_id=run.id,
        run_type=run.run_type,
        status=run.status,
        org_id=run.org_id,
        created_at=run.created_at.isoformat(),
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        result=run.result,
        error=run.error,
        prompt_tokens=run.prompt_tokens,
        completion_tokens=run.completion_tokens,
    )


def _input_hash(run_type: str, input_ref: str | None, metadata: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"run_type": run_type, "input_ref": input_ref, "metadata": metadata},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()

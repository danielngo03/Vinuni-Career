from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.access.api.identity import get_active_identity
from app.modules.ai_operations.api.legacy_schemas import (
    AIUsageLogView,
    ChatRequestPayload,
    ChatResponsePayload,
    EmbedRequest,
    EmbedResponse,
    JobPolicyRequest,
    JobPolicyResponse,
    MatchRequest,
    MatchResponse,
    ProviderStatus,
    RerankRequestPayload,
    RerankResponsePayload,
    UsageSummary,
)
from app.modules.ai_operations.application.legacy_ai_service import (
    chat_with_gateway,
    embed_with_gateway,
    evaluate_job_policy,
    log_ai_usage,
    match_cv_to_job,
    provider_status,
    rerank_with_gateway,
    usage_summary,
)
from app.platform.database.models import AIUsageLog, Job, User, UserOrgRole
from app.platform.database.session import get_db
from app.shared.errors import AppError, ErrorCode

router = APIRouter()


@router.get("/providers", response_model=ProviderStatus)
def providers(_: User = Depends(get_current_user)) -> dict[str, list[str]]:
    return provider_status()


@router.post("/chat", response_model=ChatResponsePayload)
def chat(
    payload: ChatRequestPayload,
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = chat_with_gateway(
        [message.model_dump() for message in payload.messages],
        model=payload.model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    log_ai_usage(
        db,
        org_id=identity.org_id,
        user_id=current_user.id,
        feature_name="llm_chat",
        input_text="\n".join(message.content for message in payload.messages),
        output_text=result["content"],
        provider=result["provider"],
        model=result["model"],
        request_id=result.get("request_id"),
        raw_usage=result.get("raw_usage"),
    )
    db.commit()
    return result


@router.post("/embed", response_model=EmbedResponse)
def embed(
    payload: EmbedRequest,
    _: User = Depends(get_current_user),
) -> dict:
    return embed_with_gateway(payload.text, model=payload.model)


@router.post("/rerank", response_model=RerankResponsePayload)
def rerank(
    payload: RerankRequestPayload,
    _: User = Depends(get_current_user),
) -> dict:
    return rerank_with_gateway(
        query=payload.query,
        documents=payload.documents,
        top_n=payload.top_n,
        model=payload.model,
    )


@router.post("/match", response_model=MatchResponse)
def match(
    payload: MatchRequest,
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MatchResponse:
    result = match_cv_to_job(payload.cv_text, payload.job_description)
    log_ai_usage(
        db,
        org_id=identity.org_id,
        user_id=current_user.id,
        feature_name="ad_hoc_match",
        input_text=f"{payload.cv_text}\n{payload.job_description}",
        output_text=str(result.model_dump()),
    )
    db.commit()
    return result


@router.post("/evaluate-job", response_model=JobPolicyResponse)
def evaluate_job(
    payload: JobPolicyRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    description = payload.job_description
    if payload.job_id:
        job = db.get(Job, payload.job_id)
        if not job:
            raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
        description = job.description
    if not description:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="job_id or job_description is required",
            status_code=400,
        )
    approved, reasons, trace = evaluate_job_policy(description)
    return {"approved": approved, "reasons": reasons, "trace": trace}


@router.get("/usage", response_model=UsageSummary)
def get_usage(
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    return usage_summary(db, identity.org_id)


@router.get("/usage/logs", response_model=list[AIUsageLogView])
def usage_logs(
    limit: int = Query(default=50, ge=1, le=200),
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[AIUsageLog]:
    stmt = (
        select(AIUsageLog)
        .where(AIUsageLog.org_id == identity.org_id)
        .order_by(AIUsageLog.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))

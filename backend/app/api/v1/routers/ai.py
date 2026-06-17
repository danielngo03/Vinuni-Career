from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.infra.database.models import User
from app.infra.database.session import get_db
from app.schemas.ai import (
    ChatRequestPayload,
    ChatResponsePayload,
    EmbedRequest,
    EmbedResponse,
    MatchRequest,
    MatchResponse,
    ProviderStatus,
    UsageSummary,
)
from app.services.ai_service import (
    chat_with_gateway,
    embed_with_gateway,
    log_ai_usage,
    match_cv_to_job,
    provider_status,
    usage_summary,
)

router = APIRouter()


@router.get("/providers", response_model=ProviderStatus)
def providers(_: User = Depends(get_current_user)) -> dict[str, list[str]]:
    return provider_status()


@router.post("/chat", response_model=ChatResponsePayload)
def chat(
    payload: ChatRequestPayload,
    org_id: str = Query(...),
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
        org_id=org_id,
        user_id=current_user.id,
        feature_name="llm_chat",
        input_text="\n".join(message.content for message in payload.messages),
        output_text=result["content"],
    )
    db.commit()
    return result


@router.post("/embed", response_model=EmbedResponse)
def embed(
    payload: EmbedRequest,
    _: User = Depends(get_current_user),
) -> dict:
    return embed_with_gateway(payload.text, model=payload.model)


@router.post("/match", response_model=MatchResponse)
def match(
    payload: MatchRequest,
    org_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MatchResponse:
    result = match_cv_to_job(payload.cv_text, payload.job_description)
    log_ai_usage(
        db,
        org_id=org_id,
        user_id=current_user.id,
        feature_name="ad_hoc_match",
        input_text=f"{payload.cv_text}\n{payload.job_description}",
        output_text=str(result.model_dump()),
    )
    db.commit()
    return result


@router.get("/usage", response_model=UsageSummary)
def get_usage(
    org_id: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    return usage_summary(db, org_id)

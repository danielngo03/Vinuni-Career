from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import get_current_user
from app.infra.database.models import User
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_service import search_documents

router = APIRouter()


@router.post("", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    _: User = Depends(get_current_user),
) -> SearchResponse:
    return search_documents(payload)

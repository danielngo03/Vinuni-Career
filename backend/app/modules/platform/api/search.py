from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.access.api.auth import get_current_user
from app.modules.platform.application.search_service import search_documents
from app.modules.platform.schemas import SearchRequest, SearchResponse
from app.platform.database.models import User

router = APIRouter()


@router.post("", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    _: User = Depends(get_current_user),
) -> SearchResponse:
    return search_documents(payload)

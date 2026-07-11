"""Talent Pool AI semantic search HTTP routes.

Router is HTTP-only: validate, delegate to the service (which enforces RBAC via
the ``candidate_identity:view_cv`` capability + audit + consent/visibility scope +
metering + deterministic fallback), and shape the response envelope. No
provider/model/token/cosine internals ever leave the service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.talent_pool.api.schemas import TalentSearchRequest
from app.modules.talent_pool.application import talent_search_service
from app.shared.responses import success

router = APIRouter(prefix="/talent-pool", tags=["talent-pool"])


@router.post("/search", summary="AI semantic candidate search over the consented CV pool")
async def search_talent_pool(
    body: TalentSearchRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    accept_language: str | None = Header(default=None),
) -> dict:
    """Rank consented candidates for a hiring need.

    Accepts free-text ``query_text``, an EXTERNAL pasted ``jd_text`` (a job not yet
    posted), and/or ``skills`` + ``min_experience`` filters. Returns ranked
    candidate cards with a categorical ``match_tier`` and human-readable
    ``match_reasons`` — NEVER a raw score, provider, model, or token.

    Uploaded-JD-FILE path (follow-up wiring): add a sibling multipart endpoint that
    runs ``app.ai.extraction.jd.cascade.run_jd_cascade(filename, data)`` to extract
    the JD text, then calls ``search_talent`` with the extracted text as
    ``jd_text`` — the ranking/rerank pipeline is identical from there.
    """

    locale = (accept_language or "vi").split(",")[0].split("-")[0].strip()
    data = await talent_search_service.search_talent(
        session,
        principal=auth.principal,
        ctx=auth.ctx,
        query_text=body.query_text,
        jd_text=body.jd_text,
        skills=body.skills,
        min_experience=body.min_experience,
        limit=body.limit,
        offset=body.offset,
        locale=locale,
    )
    return success(data)

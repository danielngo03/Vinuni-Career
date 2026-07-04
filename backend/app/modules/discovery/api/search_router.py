"""Search keyword logging and popular-keywords API.

Public:
  POST /api/v1/search/log     — fire-and-forget keyword logging (204 No Content)
  GET  /api/v1/search/popular — personalized popular keywords (session-first, then global 30-day)

Personalization logic:
  1. If request carries a valid discovery session cookie with recent searches → return those
     first (personal history)
  2. Fill remainder from global top queries (30-day window, same locale)
  3. If both empty → return [] (frontend must show nothing, not static fallbacks)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.modules.discovery.domain.search_log_model import SearchLog
from app.shared.responses import success

router = APIRouter(prefix="/search", tags=["search"])


class SearchLogRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    locale: str = Field(default="vi", max_length=10)


def _parse_cookie_id(raw: str | None) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(raw.strip())
    except (ValueError, AttributeError):
        return None


@router.post("/log", status_code=204, summary="Log a search query")
async def log_search(
    body: SearchLogRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> None:
    q = body.query.strip()
    if not q:
        return
    cookie_id = _parse_cookie_id(
        request.cookies.get(get_settings().discovery_session_cookie_name)
    )
    db.add(SearchLog(query=q, locale=body.locale, session_id=cookie_id))
    await db.commit()


@router.get("/popular", summary="Personalized popular search keywords")
async def popular_keywords(
    request: Request,
    locale: str = Query(default="vi", max_length=10),
    limit: int = Query(default=8, ge=1, le=30),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return keywords personalized by session, falling back to global popular.

    Algorithm:
    1. Session-recent: last 7 days of searches by this session (most recent first), distinct.
    2. Global-popular: most-searched queries in the last 30 days by locale, excluding any
       already returned from step 1.
    3. Combine up to `limit` items. If total is 0 → return [].
    """
    now = datetime.now(UTC)
    cookie_id = _parse_cookie_id(
        request.cookies.get(get_settings().discovery_session_cookie_name)
    )

    session_keywords: list[str] = []
    if cookie_id is not None:
        session_cutoff = now - timedelta(days=7)
        rows = await db.execute(
            select(SearchLog.query)
            .where(
                SearchLog.session_id == cookie_id,
                SearchLog.created_at >= session_cutoff,
            )
            .order_by(SearchLog.created_at.desc())
            .limit(limit)
        )
        # Deduplicate preserving most-recent-first order
        seen: set[str] = set()
        for (q,) in rows.all():
            lower = q.lower()
            if lower not in seen:
                seen.add(lower)
                session_keywords.append(q)

    remaining = limit - len(session_keywords)
    global_keywords: list[str] = []
    if remaining > 0:
        global_cutoff = now - timedelta(days=30)
        exclude = {k.lower() for k in session_keywords}
        global_rows = await db.execute(
            select(SearchLog.query, func.count(SearchLog.query).label("cnt"))
            .where(SearchLog.locale == locale, SearchLog.created_at >= global_cutoff)
            .group_by(SearchLog.query)
            .order_by(func.count(SearchLog.query).desc())
            .limit(limit * 3)  # fetch extra to allow dedup filtering
        )
        for (q, _) in global_rows.all():
            if len(global_keywords) >= remaining:
                break
            if q.lower() not in exclude:
                global_keywords.append(q)
                exclude.add(q.lower())

    return success({"keywords": session_keywords + global_keywords})

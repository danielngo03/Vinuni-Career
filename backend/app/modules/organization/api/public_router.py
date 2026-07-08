"""Public (unauthenticated) company directory routes under ``/api/v1/companies``.

HTTP-only: validate query/path and delegate to
:mod:`company_directory_service`, which enforces the public-only projection
(active partners). No auth is required — this is a guest marketplace surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.organization.application import company_directory_service, logo_service
from app.shared.responses import success

companies_router = APIRouter(prefix="/companies", tags=["companies"])


@companies_router.get("", summary="Public company directory (active partners only)")
async def list_companies(
    session: AsyncSession = Depends(get_db_session),
    q: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
) -> dict:
    items, next_cursor, page_limit, total = await company_directory_service.list_companies(
        session, q=q, industry=industry, cursor=cursor, limit=limit,
    )
    return {
        "data": items,
        "page": {"next_cursor": next_cursor, "limit": page_limit, "total": total},
    }


@companies_router.get(
    "/{slug}/logo",
    summary="Public company logo (active partners only)",
    response_class=Response,
)
async def get_company_logo(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    logo = await logo_service.serve_logo(session, slug=slug)
    return Response(
        content=logo.content,
        media_type=logo.media_type,
        headers={
            # Public marketing asset. The resolved ``logo_url`` carries a
            # ``?v=`` cache key, so a long-but-revalidatable cache is safe.
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": "inline",
        },
    )


@companies_router.get("/{slug}", summary="Public company profile + open roles")
async def get_company(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await company_directory_service.get_company(session, slug=slug)
    return success(data)

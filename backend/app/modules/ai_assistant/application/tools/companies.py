"""Company-related AI tool handlers (search, detail, reviews)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.permissions import Principal


async def search_companies(session: AsyncSession, principal: Principal, args: dict) -> dict:
    from app.modules.organization.application import company_directory_service

    q = args.get("q") or None
    industry = args.get("industry") or None
    items, _next, _limit, _total = await company_directory_service.list_companies(
        session, q=q, industry=industry, cursor=None, limit=5
    )
    return {
        "ok": True,
        "companies": [
            {
                "id": str(c.get("id", "")),
                "name": c.get("display_name", ""),
                "industry": c.get("industry") or "",
                "is_verified": c.get("is_verified", False),
                "open_roles": c.get("active_job_count", 0),
                "url": f"/companies/{c.get('slug', c.get('id', ''))}",
            }
            for c in items[:5]
        ],
        "total": _total,
    }


async def get_company_detail(session: AsyncSession, principal: Principal, args: dict) -> dict:
    from app.modules.organization.application import company_directory_service

    slug = str(args.get("slug", "")).strip()
    if not slug:
        return {"ok": False, "error": "slug_required"}
    detail = await company_directory_service.get_company(session, slug=slug)
    rating = detail.get("rating") or {}
    return {
        "ok": True,
        "company": {
            "name": detail.get("display_name", ""),
            "industry": detail.get("industry", ""),
            "size": detail.get("company_size", ""),
            "city": detail.get("headquarters_city", ""),
            "open_job_count": detail.get("active_job_count", 0),
            "rating": rating.get("overall_avg"),
            "review_count": rating.get("review_count", 0),
            "description": (detail.get("description") or "")[:300],
            "is_verified": detail.get("is_verified", False),
            "url": f"/companies/{slug}",
        },
    }


async def get_company_reviews(session: AsyncSession, principal: Principal, args: dict) -> dict:
    from app.modules.organization.application import org_lookup_facade
    from app.modules.reviews.application import review_service
    from app.modules.reviews.application.company_rating_facade import ratings_for

    slug = (args.get("slug") or "").strip()
    if not slug:
        return {"ok": False, "error": "slug_required"}
    try:
        org_id = await org_lookup_facade.listable_id_for_slug(session, slug=slug)
        if org_id is None:
            return {"ok": False, "error": "company_not_found"}
        rating_map = await ratings_for(session, [org_id])
        rating = rating_map.get(org_id)
        reviews_result = await review_service.list_public_reviews(
            session, slug=slug, principal=principal, limit=3
        )
    except Exception:
        return {"ok": False, "error": "tool_failed"}
    return {
        "ok": True,
        "company_slug": slug,
        "rating": rating,
        "recent_reviews": [
            {
                "author": r.get("author_name", ""),
                "overall": r.get("overall_score"),
                "summary": (r.get("summary") or "")[:200],
                "pros": (r.get("pros") or "")[:200],
                "cons": (r.get("cons") or "")[:200],
            }
            for r in reviews_result.get("items", [])[:3]
        ],
        "url": f"/companies/{slug}",
    }

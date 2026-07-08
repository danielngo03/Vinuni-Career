"""Job-related AI tool handlers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.permissions import Principal


async def _combined_cv_query_text(
    session: AsyncSession,
    principal: Principal,
    *,
    limit: int = 5,
) -> str:
    """Build a search query from the student's whole CV library, not one arbitrary CV."""

    from app.ai.cv import grounding
    from app.modules.documents.application import cv_ranking_facade

    cv_inputs = await cv_ranking_facade.build_cv_inputs(session, principal=principal)
    parts: list[str] = []
    for cv in cv_inputs[:limit]:
        text = grounding.sections_to_text(cv.sections)
        if text.strip():
            parts.append(f"{cv.title}\n{text}")
    return "\n\n".join(parts)[:2500]


async def recommended_cv_id_for_job(
    session: AsyncSession, principal: Principal, job_id
) -> str | None:
    """Return the highest scoring CV for a visible job, or None when no CV exists."""

    from app.ai.cv import job_fit
    from app.core.config import get_settings
    from app.modules.documents.application import cv_ranking_facade
    from app.modules.opportunities.application import job_fit_read

    job = await job_fit_read.load_job_for_fit(
        session, job_id=job_id, persona=principal.persona or "student"
    )
    if job is None:
        return None
    cv_inputs = await cv_ranking_facade.build_cv_inputs(session, principal=principal)
    if not cv_inputs:
        return None
    outcome = job_fit.evaluate(
        job,
        cv_inputs,
        stale_days=get_settings().cv_stale_after_days,
    )
    return outcome.recommended_cv_id


async def search_jobs(session: AsyncSession, principal: Principal, args: dict) -> dict:
    from app.modules.opportunities.application import job_service

    q = args.get("q") or None
    province_code = args.get("province_code") or None
    items, _next, _limit, _total = await job_service.list_public_jobs(
        session, principal=principal, q=q, cursor=None, limit=5, province_code=province_code
    )
    return {
        "ok": True,
        "jobs": [
            {
                "id": str(j.get("id", "")),
                "title": j.get("title", ""),
                "company": (j.get("company") or {}).get("display_name", ""),
                "city": (
                    (j.get("locations") or [{}])[0].get("city", "")
                    if j.get("locations")
                    else j.get("headquarters_city", "")
                ),
                "url": f"/jobs/{j.get('id', '')}",
            }
            for j in items[:5]
        ],
    }


async def get_job_detail(session: AsyncSession, principal: Principal, args: dict) -> dict:
    import uuid as _uuid

    from app.modules.opportunities.application import job_service

    raw = (args.get("job_id") or "").strip()
    try:
        job_id = _uuid.UUID(raw)
    except ValueError:
        return {"ok": False, "error": "invalid_job_id"}
    try:
        detail = await job_service.get_job(session, principal=principal, job_id=job_id)
    except Exception:
        return {"ok": False, "error": "tool_failed"}
    return {
        "ok": True,
        "job": {
            "id": str(detail.get("id", "")),
            "title": detail.get("title", ""),
            "company": (detail.get("company") or {}).get("display_name", ""),
            "employment_type": (
                detail.get("employment_type_label") or detail.get("employment_type", "")
            ),
            "location_type": detail.get("location_type_label") or detail.get("location_type", ""),
            "description": (detail.get("description") or "")[:600],
            "requirements": (detail.get("requirements") or "")[:400],
            "benefits": (detail.get("benefits") or "")[:400],
            "salary_min": detail.get("salary_min"),
            "salary_max": detail.get("salary_max"),
            "salary_currency": detail.get("salary_currency"),
            "salary_is_disclosed": detail.get("salary_is_disclosed", False),
            "required_skills": detail.get("required_skills", [])[:10],
            "application_deadline": detail.get("application_deadline"),
            "url": f"/jobs/{detail.get('id', '')}",
        },
    }


async def get_job_alerts(session: AsyncSession, principal: Principal) -> dict:
    from app.modules.opportunities.application import job_alert_service

    try:
        alerts = await job_alert_service.list_alerts(session, principal=principal)
    except Exception:
        return {"ok": False, "error": "tool_failed"}
    return {
        "ok": True,
        "alerts": [
            {
                "name": a.get("name", ""),
                "keywords": a.get("keywords") or None,
                "employment_type": a.get("employment_type") or None,
                "location_type": a.get("location_type") or None,
                "last_sent_at": a.get("last_sent_at") or None,
                "manage_url": "/student/alerts",
            }
            for a in alerts[:10]
        ],
        "total": len(alerts),
        "manage_url": "/student/alerts",
    }


async def get_saved_jobs(session: AsyncSession, principal: Principal) -> dict:
    from app.modules.opportunities.application import saved_jobs_service

    items, _next, _limit = await saved_jobs_service.list_saved_jobs(
        session, principal=principal, cursor=None, limit=5
    )
    return {
        "ok": True,
        "saved_jobs": [
            {
                "id": str(j.get("id", "")),
                "title": j.get("title", ""),
                "company": (j.get("company") or {}).get("display_name", ""),
                "status": j.get("status", ""),
                "url": f"/jobs/{j.get('id', '')}",
            }
            for j in items[:5]
        ],
    }


async def get_partner_jobs(session: AsyncSession, principal: Principal, args: dict) -> dict:
    from app.modules.opportunities.application import job_service

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}
    status_filter = (args.get("status") or "").strip() or None
    try:
        items, _next, _limit = await job_service.list_my_jobs(
            session, principal=principal, status=status_filter, cursor=None, limit=10
        )
    except Exception:
        return {"ok": False, "error": "tool_failed"}
    return {
        "ok": True,
        "job_count": len(items),
        "jobs": [
            {
                "id": str(j.get("id", "")),
                "title": j.get("title", ""),
                "status": j.get("status", ""),
                "application_count": j.get("application_count", 0),
                "deadline": j.get("application_deadline"),
                "url": f"/partner/jobs/{j.get('id', '')}",
            }
            for j in (items or [])[:10]
        ],
    }


async def recommend_jobs(session: AsyncSession, principal: Principal, args: dict) -> dict:
    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    limit = min(int(args.get("limit") or 5), 10)
    try:
        from app.modules.opportunities.application import job_service

        query_text = await _combined_cv_query_text(session, principal, limit=5)

        from app.ai.retrieval.hybrid_search import hybrid_job_search
        from app.ai.retrieval.rerank import rerank_jobs

        if query_text.strip():
            fused = await hybrid_job_search(session, query=query_text, limit=limit * 3)
            job_docs: dict = {}
            for jid, _ in fused:
                try:
                    d = await job_service.get_job(session, principal=principal, job_id=jid)
                    skills = ", ".join((d.get("required_skills") or [])[:5])
                    job_docs[jid] = f"{d.get('title', '')} {skills}"[:200]
                except Exception:
                    job_docs[jid] = str(jid)
            reranked = await rerank_jobs(query_text, job_docs, top_k=limit, db=session)
            job_ids = [jid for jid, _ in reranked]
            source = "cv_match_reranked"
        else:
            items, _, _, _ = await job_service.list_public_jobs(
                session, principal=principal, cursor=None, limit=limit
            )
            job_ids = [item["id"] for item in items if item.get("id")]
            source = "recent"

        recommendations = []
        for jid in job_ids[:limit]:
            try:
                detail = await job_service.get_job(session, principal=principal, job_id=jid)
                recommendations.append({
                    "id": str(jid),
                    "title": detail.get("title", ""),
                    "company": (detail.get("company") or {}).get("display_name", ""),
                    "employment_type": (
                        detail.get("employment_type_label")
                        or detail.get("employment_type", "")
                    ),
                    "location_type": (
                        detail.get("location_type_label") or detail.get("location_type", "")
                    ),
                    "url": f"/jobs/{jid}",
                })
            except Exception:
                continue
        return {"ok": True, "recommendations": recommendations, "source": source}
    except Exception:
        return {"ok": False, "error": "tool_failed"}


async def save_job(session: AsyncSession, principal: Principal, args: dict) -> dict:
    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    import uuid as _uuid

    job_id_str = (args.get("job_id") or "").strip()
    if not job_id_str:
        return {"ok": False, "error": "job_id_required"}
    try:
        job_id = _uuid.UUID(job_id_str)
    except ValueError:
        return {"ok": False, "error": "invalid_job_id"}
    try:
        from app.modules.opportunities.application import saved_jobs_service
        await saved_jobs_service.save_job(session, principal=principal, job_id=job_id)
        return {"ok": True, "saved": True, "job_id": job_id_str}
    except Exception:
        return {"ok": False, "error": "save_failed", "job_id": job_id_str}


async def apply_job(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Submit an application on the student's behalf.

    This is a mutating tool: the assistant must have already surfaced the
    confirmation card (§4.3) before this executes. ``cv_id`` names one of the
    student's own CV profiles; the currently accepted version of that CV is
    used as the immutable application snapshot (``documents`` module contract).
    """
    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    import uuid as _uuid

    job_id_str = (args.get("job_id") or "").strip()
    cv_id_str = (args.get("cv_id") or "").strip()
    if not job_id_str:
        return {"ok": False, "error": "job_id_required"}
    try:
        job_id = _uuid.UUID(job_id_str)
    except ValueError:
        return {"ok": False, "error": "invalid_job_id"}
    try:
        from app.modules.auth.application.context import RequestContext
        from app.modules.documents.application import cv_service
        from app.modules.recruitment.application import apply_service

        if cv_id_str:
            try:
                cv_id = _uuid.UUID(cv_id_str)
            except ValueError:
                return {"ok": False, "error": "invalid_cv_id"}
        else:
            best_cv_id = await recommended_cv_id_for_job(session, principal, job_id)
            if best_cv_id is None:
                return {"ok": False, "error": "no_cv_found", "job_id": str(job_id)}
            cv_id = _uuid.UUID(str(best_cv_id))

        cv_detail = await cv_service.get_cv(session, principal=principal, cv_id=cv_id)
        current_version_id = cv_detail.get("current_version_id")
        if not current_version_id:
            return {"ok": False, "error": "cv_has_no_version", "job_id": str(job_id)}

        result = await apply_service.apply_to_job(
            session,
            principal=principal,
            payload={
                "job_id": str(job_id),
                "cv_selection": {
                    "type": "builder_cv",
                    "cv_profile_id": str(cv_id),
                    "cv_version_id": current_version_id,
                },
            },
            ctx=RequestContext(),
        )
        return {
            "ok": True,
            "applied": True,
            "job_id": str(job_id),
            "application_id": str(result.get("id", "")),
        }
    except Exception as exc:
        err = str(exc)
        if "already" in err.lower() or "duplicate" in err.lower():
            return {"ok": False, "error": "already_applied", "job_id": str(job_id)}
        return {"ok": False, "error": "apply_failed", "job_id": str(job_id)}

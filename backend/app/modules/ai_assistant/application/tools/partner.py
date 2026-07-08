"""Partner-only AI tool handlers.

Scope (AI_PRODUCT_SPEC.md §7, partner assistant spec): every handler here only
ever reads/writes the CALLING partner's own organisation. RBAC is delegated to
the underlying service (``permission_checker.require`` + org-ownership loads
already implemented in ``recruitment``/``opportunities``) — handlers never
trust a client-supplied org id, only ``principal.org_id`` and rows loaded and
org-checked by the service layer. All CV-generation tools return DRAFTS only
(never persisted) and confidence is a label (``high``/``medium``/``low``),
never a raw float. ``move_candidate_stage`` is the only mutating tool and is
gated ``confirmation_required`` in ``specs.py``.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.exceptions import AuthRequiredError, PermissionDeniedError, ResourceNotFoundError
from app.shared.permissions import Principal


def _parse_uuid(raw: str | None) -> _uuid.UUID | None:
    if not raw:
        return None
    try:
        return _uuid.UUID(str(raw).strip())
    except ValueError:
        return None


# Human-friendly labels for pipeline statuses — the chat surface must not leak
# raw enum codes (backend rule: "No raw enum codes in end-user responses").
_FUNNEL_STAGE_LABELS: dict[str, str] = {
    "submitted": "Submitted",
    "under_review": "Under review",
    "shortlisted": "Shortlisted",
    "interview": "Interview",
    "offer": "Offer",
    "hired": "Hired",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
}


async def get_partner_pipeline_summary(session: AsyncSession, principal: Principal) -> dict:
    from app.modules.recruitment.application import dashboard_read as recruitment_read

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}
    try:
        rows = await recruitment_read.pipeline_overview_for_org(
            session, org_id=principal.org_id, limit=20
        )
    except Exception:
        return {"ok": False, "error": "tool_failed"}
    total_active = sum(r.get("active_total", 0) for r in rows)
    return {
        "ok": True,
        "total_active_candidates": total_active,
        "job_count": len(rows),
        "jobs": [
            {
                "title": r.get("title", ""),
                "status": r.get("status", ""),
                "active_candidates": r.get("active_total", 0),
                "rejected": r.get("rejected", 0),
                "withdrawn": r.get("withdrawn", 0),
                "total": r.get("total", 0),
                "url": "/partner/pipeline",
            }
            for r in rows[:10]
        ],
    }


async def search_partner_candidates(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Search/shortlist the org's own applicants for one job (by stage/keyword).

    Reuses ``apply_service.list_job_applications`` — it already 404s on a
    cross-org ``job_id`` and redacts identity for anonymous-apply applicants
    (``presenters.partner_application`` / ``_applicant_identity``). Only the
    candidate's display label is returned here (never email), to keep the
    chat surface's PII footprint smaller than the full pipeline UI.
    """
    from app.modules.recruitment.application import apply_service

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    job_id = _parse_uuid(args.get("job_id"))
    if job_id is None:
        return {"ok": False, "error": "job_id_required"}

    stage_filter = (args.get("stage") or "").strip().lower() or None
    q = (args.get("q") or "").strip().lower() or None

    try:
        items, _next, _limit = await apply_service.list_job_applications(
            session, principal=principal, job_id=job_id, cursor=None, limit=25
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    results = []
    for a in items:
        status = (a.get("status") or "").lower()
        if stage_filter and stage_filter not in status:
            continue
        applicant = a.get("applicant") or {}
        label = applicant.get("display_name") or "Candidate"
        if q and q not in label.lower():
            continue
        results.append(
            {
                "application_id": a.get("id"),
                "status": a.get("status_label") or a.get("status"),
                "is_anonymous": applicant.get("is_anonymous", True),
                "candidate_label": label,
                "applied_at": a.get("applied_at"),
                "url": f"/partner/pipeline/applications/{a.get('id', '')}",
            }
        )
    return {
        "ok": True,
        "job_id": str(job_id),
        "candidates": results[:15],
        "total": len(results),
    }


async def get_candidate_detail(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Single applicant's stage/scorecard-gate/CV-snapshot link (not raw bytes).

    Delegates to ``apply_service.get_application`` for org-ownership + identity
    redaction — it raises ``ResourceNotFoundError`` for a cross-org application,
    which is indistinguishable from a missing one (tenant-isolation convention).
    """
    from app.modules.recruitment.application import apply_service

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    application_id = _parse_uuid(args.get("application_id"))
    if application_id is None:
        return {"ok": False, "error": "application_id_required"}

    try:
        view = await apply_service.get_application(
            session, principal=principal, application_id=application_id
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    applicant = view.get("applicant") or {}
    pipeline = view.get("pipeline") or {}
    current_stage = pipeline.get("current_stage") or {}
    return {
        "ok": True,
        "application_id": view.get("id"),
        "job_id": view.get("job_id"),
        "status": view.get("status_label") or view.get("status"),
        "candidate_label": applicant.get("display_name"),
        "is_anonymous": applicant.get("is_anonymous", True),
        "current_stage": current_stage.get("name"),
        "cv_snapshot_available": bool(view.get("snapshot_id")),
        "cv_download_available": view.get("cv_download_available", False),
        "applied_at": view.get("applied_at"),
        "url": f"/partner/pipeline/applications/{view.get('id', '')}",
    }


async def draft_job_description(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """LLM draft only — never persisted. The partner must review/edit/apply it."""
    from app.modules.opportunities.application import jd_ai_service

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    title = (args.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "title_required"}

    payload = {
        "title": title,
        "employment_type": args.get("employment_type"),
        "experience_level": args.get("experience_level"),
        "location": args.get("location"),
        "required_skills": args.get("required_skills"),
        "preferred_skills": args.get("preferred_skills"),
        "responsibilities": args.get("responsibilities"),
        "benefits": args.get("benefits"),
        "partner_instruction": args.get("partner_instruction"),
    }
    try:
        result = await jd_ai_service.draft_description_standalone(
            session, principal=principal, payload=payload
        )
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    bias = result.get("bias_check") or {}
    return {
        "ok": True,
        "draft": result.get("draft", ""),
        "bias_flagged": bias.get("flagged", False),
        "requires_human_review": bias.get("requires_human_review", False),
        "note": "Draft only — review and edit before creating the job posting.",
    }


async def rewrite_job_description(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """LLM redraft of an EXISTING org-owned job — never persisted directly."""
    from app.modules.opportunities.application import jd_ai_service

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    job_id = _parse_uuid(args.get("job_id"))
    if job_id is None:
        return {"ok": False, "error": "job_id_required"}

    payload = {
        k: v
        for k, v in args.items()
        if k in ("employment_type", "experience_level", "location", "required_skills",
                  "preferred_skills", "responsibilities", "benefits", "partner_instruction")
    }
    try:
        result = await jd_ai_service.draft_description(
            session, principal=principal, job_id=job_id, payload=payload
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    bias = result.get("bias_check") or {}
    return {
        "ok": True,
        "draft": result.get("draft", ""),
        "bias_flagged": bias.get("flagged", False),
        "requires_human_review": bias.get("requires_human_review", False),
        "note": "Draft only — review and edit before saving changes to the job.",
    }


async def check_jd_bias(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Deterministic, offline bias/discrimination scan over JD text (no LLM call).

    Operates on caller-supplied text only (a draft or a pasted existing
    description) — no job lookup is performed, so there is no org-ownership
    question to resolve for this read-only, zero-cost check.
    """
    from app.ai.safety.bias_detection import check_bias

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    text = (args.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "text_required"}

    result = check_bias(text[:6000])
    return {"ok": True, **result.as_dict()}


async def suggest_scorecard(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Advisory scorecard suggestion from interviewer notes — never persisted."""
    from app.modules.recruitment.application import scorecard_ai_service

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    application_id = _parse_uuid(args.get("application_id"))
    notes = (args.get("notes") or "").strip()
    if application_id is None or not notes:
        return {"ok": False, "error": "application_id_and_notes_required"}

    try:
        result = await scorecard_ai_service.suggest_scorecard(
            session,
            principal=principal,
            application_id=application_id,
            notes=notes,
            job_title=args.get("job_title"),
            interview_stage=args.get("interview_stage"),
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    return {
        "ok": True,
        "criteria": result.get("criteria", {}),
        "recommendation": result.get("recommendation"),
        "overall_reasoning": result.get("overall_reasoning", ""),
        "confidence": result.get("confidence", "low"),
        "is_fallback": result.get("is_fallback", False),
        "note": "Draft suggestion only — the interviewer must review and submit the scorecard.",
    }


async def generate_screening_brief(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """3-4 bullet privacy-safe CV-vs-role screening brief. Advisory only."""
    from app.modules.recruitment.application import screening_brief_service

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    application_id = _parse_uuid(args.get("application_id"))
    if application_id is None:
        return {"ok": False, "error": "application_id_required"}

    try:
        result = await screening_brief_service.generate_screening_brief(
            session, principal=principal, application_id=application_id
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    return {
        "ok": True,
        "bullets": result.get("bullets", []),
        "suitability": result.get("suitability"),
        "is_fallback": result.get("is_fallback", False),
    }


async def get_upcoming_partner_events(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Org-hosted events summary (all statuses), soonest first."""
    from app.modules.opportunities.application import event_service

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    try:
        items, _next, _limit = await event_service.list_my_events(
            session, principal=principal, cursor=None, limit=25
        )
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    now = datetime.now(UTC)
    upcoming = []
    for e in items:
        starts_at = e.get("starts_at")
        starts_dt = None
        if starts_at:
            try:
                starts_dt = datetime.fromisoformat(starts_at)
                if starts_dt.tzinfo is None:
                    starts_dt = starts_dt.replace(tzinfo=UTC)
            except ValueError:
                starts_dt = None
        if starts_dt is not None and starts_dt < now:
            continue
        upcoming.append(
            {
                "id": e.get("id"),
                "title": e.get("title", ""),
                "status": e.get("status_label") or e.get("status", ""),
                "starts_at": starts_at,
                "registration_count": e.get("registration_count", 0),
                "url": f"/partner/events/{e.get('id', '')}",
            }
        )
    upcoming.sort(key=lambda x: x["starts_at"] or "")
    return {"ok": True, "events": upcoming[:8], "total": len(upcoming)}


async def get_partner_analytics_summary(session: AsyncSession, principal: Principal) -> dict:
    """Org-scoped hiring analytics summary — funnel, top jobs, conversion.

    Reuses the SAME read functions that power ``GET /dashboards/partner/analytics``
    (``recruitment.dashboard_read.analytics_*``); no new SQL/aggregation is
    written here. Every count is scoped to the caller's own ``principal.org_id``
    and is aggregate-only — no candidate PII, no raw scores, no provider/model
    internals. Dispatch RBAC (``specs.py`` ``required_permissions`` including
    ``analytics:view_job_metrics``) gates access; this handler keeps the standard
    partner auth/org guard as defense-in-depth.
    """
    from app.modules.recruitment.application import dashboard_read as recruitment_read

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    org_id = principal.org_id
    try:
        funnel_rows = await recruitment_read.analytics_application_funnel(session, org_id=org_id)
        top_jobs = await recruitment_read.analytics_top_jobs(session, org_id=org_id, limit=5)
        monthly = await recruitment_read.analytics_monthly_trend(session, org_id=org_id)
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    count_by_status = {r["status"]: int(r["count"]) for r in funnel_rows}
    # Each application has exactly one current status, so the funnel counts sum
    # to the org's total application volume.
    applications_total = sum(count_by_status.values())

    def _rate(n: int) -> float | None:
        if applications_total <= 0:
            return None
        return round(n * 100 / applications_total, 1)

    return {
        "ok": True,
        "applications_total": applications_total,
        "funnel": [
            {
                "stage": _FUNNEL_STAGE_LABELS.get(
                    r["status"], str(r["status"]).replace("_", " ").title()
                ),
                "count": int(r["count"]),
            }
            for r in funnel_rows
        ],
        "top_jobs": [
            {
                "title": j.get("title") or "—",
                "application_count": j.get("application_count", 0),
                "url": f"/partner/jobs/{j.get('job_id', '')}",
            }
            for j in top_jobs
        ],
        "monthly_trend": [
            {"month": m.get("month"), "applications": m.get("count", 0)} for m in monthly
        ],
        "conversion": {
            # hire_rate is the headline (terminal) conversion; interview/offer are
            # the share of applications currently at that live pipeline stage.
            "hire_rate_pct": _rate(count_by_status.get("hired", 0)),
            "offer_rate_pct": _rate(count_by_status.get("offer", 0)),
            "interview_rate_pct": _rate(count_by_status.get("interview", 0)),
        },
        "note": (
            "Aggregate counts for your organisation only — no individual candidate data."
        ),
    }


async def move_candidate_stage(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Advance the candidate to the NEXT pipeline stage (confirmation-gated).

    Wraps ``stage_service.advance_application_stage`` — the SAME validator the
    partner pipeline UI's ``/advance`` endpoint uses (org-ownership 404 gate,
    optimistic version check, required_action/scorecard-gate enforcement,
    audit row, student notification). No transition rule is duplicated here.
    """
    from app.modules.auth.application.context import RequestContext
    from app.modules.recruitment.application import stage_service
    from app.modules.recruitment.application.errors import (
        ApplicationVersionConflictError,
        IllegalApplicationTransitionError,
        ScoreBelowThresholdError,
        ScorecardRequiredError,
    )

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    application_id = _parse_uuid(args.get("application_id"))
    if application_id is None:
        return {"ok": False, "error": "application_id_required"}

    try:
        result = await stage_service.advance_application_stage(
            session,
            principal=principal,
            application_id=application_id,
            ctx=RequestContext(),
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except ApplicationVersionConflictError:
        return {"ok": False, "error": "version_conflict"}
    except (IllegalApplicationTransitionError, ScoreBelowThresholdError, ScorecardRequiredError):
        return {"ok": False, "error": "stage_gate_not_met"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    pipeline = result.get("pipeline") or {}
    current_stage = pipeline.get("current_stage") or {}
    return {
        "ok": True,
        "application_id": result.get("id"),
        "new_stage": current_stage.get("name"),
        "status": result.get("status_label") or result.get("status"),
        "url": f"/partner/pipeline/applications/{result.get('id', '')}",
    }

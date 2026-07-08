"""University-staff AI tool handlers (AI_PRODUCT_SPEC.md §7, §4 assistant).

Scope: every handler here delegates to the OWNING module's application service
/ read-model facade and never reaches into another module's domain/ORM models
(module-boundary rule). RBAC is enforced twice: the central dispatch gate
(``dispatch.authorize_tool``) pre-checks ``spec.required_permissions`` against
the caller's grants, and each underlying service does its own authoritative,
org-scoped ``permission_checker`` + ``org_type == university`` check. Handlers
therefore only translate the service result into a privacy-safe, aggregated
chat payload — no provider/model internals, no student/candidate PII beyond the
caller's grants, no raw enum codes (labels only), and no fabricated data.

Read tools return operational summaries. The two write tools
(``approve_job_moderation`` / ``request_job_changes``) are declared
``confirmation_required`` in ``specs.py`` — the chat loop returns a confirmation
card and this handler runs only after the staffer confirms. Both delegate to the
same ``opportunities.moderation_service`` the university moderation UI uses, so
every transition rule, audit row, and partner notification is reused (never
duplicated here).
"""

from __future__ import annotations

import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.exceptions import (
    AppError,
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.permissions import Principal


def _parse_uuid(raw: str | None) -> _uuid.UUID | None:
    if not raw:
        return None
    try:
        return _uuid.UUID(str(raw).strip())
    except ValueError:
        return None


def _staff_ready(principal: Principal) -> bool:
    """University-staff pre-check mirrored from the service gate (org required)."""

    return principal.is_authenticated and (
        principal.is_superadmin or principal.org_id is not None
    )


# --------------------------------------------------------------------------- #
# Read tools                                                                  #
# --------------------------------------------------------------------------- #


async def get_university_dashboard_summary(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Operations command-center rollup: queues, partner requests, next actions."""
    from app.modules.dashboards.application import university_dashboard

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}
    try:
        data = await university_dashboard.get_university_dashboard(
            session, principal=principal, locale="en"
        )
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    metrics = data.get("metrics") or {}
    return {
        "ok": True,
        "metrics": {
            "jobs_pending_moderation": metrics.get("jobs_pending_moderation", 0),
            "partners_pending": metrics.get("partners_pending", 0),
            "partners_active": metrics.get("partners_active", 0),
            "jobs_active_total": metrics.get("jobs_active_total", 0),
        },
        "next_actions": data.get("next_actions") or [],
        "url": "/university",
    }


async def get_moderation_queue(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Jobs awaiting university review, oldest first, with age/overdue SLA."""
    from app.modules.opportunities.application import moderation_service

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}

    status = (args.get("status") or "").strip().lower() or None
    try:
        items, total = await moderation_service.list_moderation_queue(
            session, principal=principal, status=status, limit=15, locale="en"
        )
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    queue = [
        {
            "job_id": it.get("id"),
            "title": it.get("title", ""),
            "status": it.get("status_label") or it.get("status"),
            "age_hours": it.get("age_hours"),
            "is_overdue": it.get("is_overdue", False),
            "due_by": it.get("due_by"),
            "url": "/university/moderation/jobs",
        }
        for it in items[:10]
    ]
    overdue = sum(1 for it in items if it.get("is_overdue"))
    return {
        "ok": True,
        "queue": queue,
        "total_pending": total,
        "overdue_count": overdue,
        "note": "Advisory summary — approving or sending a job back is a human decision.",
    }


async def get_ai_review_queue(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """AI/rule-FLAGGED jobs + events awaiting a human's final say, oldest first.

    Read-only advisory summary: each item carries a user-safe flag reason LABEL
    (never model confidence / provider / model / token internals), its age, and
    whether it is overdue against the tight AI-review SLA. Upholding or dismissing
    a flag remains a human decision made from the moderation surface.
    """
    from app.modules.opportunities.application import ai_review_queue_service

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}

    try:
        items, counts = await ai_review_queue_service.list_queue(
            session, principal=principal, limit=15, locale="en"
        )
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    queue = [
        {
            "item_type": it.get("item_type"),
            "id": it.get("id"),
            "title": it.get("title", ""),
            "flag_reason": it.get("flag_reason_label") or it.get("flag_reason_code"),
            "status": it.get("status_label") or it.get("status"),
            "age_hours": it.get("age_hours"),
            "is_overdue": it.get("is_overdue", False),
            "due_by": it.get("due_by"),
            "url": "/university/moderation",
        }
        for it in items[:10]
    ]
    overdue = sum(1 for it in items if it.get("is_overdue"))
    return {
        "ok": True,
        "queue": queue,
        "counts": counts,
        "total_flagged": counts.get("total", 0),
        "overdue_count": overdue,
        "note": (
            "Advisory summary — AI/rule flags are not decisions. Upholding "
            "(rejecting) or dismissing a flag is a human call."
        ),
    }


async def get_pending_partner_registrations(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Partner organisations awaiting university approval (governance queue)."""
    from app.modules.organization.application import partner_registration_service

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}
    try:
        rows = await partner_registration_service.list_requests(
            session, principal=principal, status="pending_review", locale="en"
        )
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    # Chat surface keeps a smaller PII footprint than the review UI: company
    # metadata only, never the partner contact's name/email.
    registrations = [
        {
            "id": r.get("id"),
            "company_name": r.get("company_name", ""),
            "industry": r.get("industry"),
            "company_size": r.get("company_size"),
            "status": r.get("status_label") or r.get("status"),
            "submitted_at": r.get("created_at"),
            "url": "/university/moderation/partners",
        }
        for r in rows[:10]
    ]
    return {"ok": True, "registrations": registrations, "total_pending": len(rows)}


async def get_partner_overview(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Partner governance rollup: active partner count + registrations by status."""
    from app.modules.organization.application import (
        company_directory_service,
        partner_registration_service,
    )

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}
    try:
        rows = await partner_registration_service.list_requests(
            session, principal=principal, status=None, locale="en"
        )
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    by_status: dict[str, int] = {}
    label_for: dict[str, str] = {}
    for r in rows:
        code = r.get("status") or "unknown"
        by_status[code] = by_status.get(code, 0) + 1
        label_for[code] = r.get("status_label") or code

    try:
        active_partners = await company_directory_service.count_public_companies(session)
    except Exception:
        active_partners = None

    return {
        "ok": True,
        "active_partners": active_partners,
        "registrations_total": len(rows),
        "registrations_by_status": [
            {"status": label_for[code], "count": n}
            for code, n in sorted(by_status.items())
        ],
        "url": "/university/partners",
    }


async def get_at_risk_students(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Career-services at-risk flags — privacy-safe aggregate + capped list.

    Never returns student names/emails: an internal ``student_ref`` (short
    opaque id) is included only so staff can locate the record in the workspace.
    """
    from app.modules.career_services.application import at_risk_service

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}
    try:
        flags = await at_risk_service.list_flags(session, principal=principal, locale="en")
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    by_severity: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for f in flags:
        sev = f.get("severity_label") or f.get("severity") or "unknown"
        st = f.get("status_label") or f.get("status") or "unknown"
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1

    recent = [
        {
            "student_ref": (f.get("student_id") or "")[:8],
            "reason": f.get("reason_label") or f.get("reason"),
            "severity": f.get("severity_label") or f.get("severity"),
            "status": f.get("status_label") or f.get("status"),
            "flagged_at": f.get("created_at"),
            "url": "/university/students/at-risk",
        }
        for f in flags[:10]
    ]
    return {
        "ok": True,
        "total_flags": len(flags),
        "by_severity": [{"severity": k, "count": v} for k, v in sorted(by_severity.items())],
        "by_status": [{"status": k, "count": v} for k, v in sorted(by_status.items())],
        "recent": recent,
        "note": "Privacy-safe summary — support opportunities, not individual private detail.",
    }


async def get_cohort_summary(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Career-services cohorts the caller's org owns, with status labels."""
    from app.modules.career_services.application import cohort_service

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}
    try:
        cohorts = await cohort_service.list_cohorts(session, principal=principal, locale="en")
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    items = [
        {
            "id": c.get("id"),
            "name": c.get("name", ""),
            "description": c.get("description"),
            "status": c.get("status_label") or c.get("status"),
            "url": "/university/students/cohorts",
        }
        for c in cohorts[:15]
    ]
    return {"ok": True, "cohorts": items, "total": len(cohorts)}


async def get_career_services_report(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Counselor-workspace aggregate report (cohorts, at-risk, CV review, appts)."""
    from app.modules.career_services.application import reporting_service

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}
    try:
        summary = await reporting_service.get_reporting_summary(
            session, principal=principal, locale="en"
        )
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    return {
        "ok": True,
        "active_cohorts": summary.get("active_cohorts", 0),
        "open_at_risk_flags": summary.get("open_at_risk_flags", 0),
        "open_cv_reviews": summary.get("open_cv_reviews", 0),
        "at_risk_by_severity": summary.get("at_risk_by_severity", []),
        "appointments_by_status": summary.get("appointments_by_status", []),
        "url": "/university/students",
    }


async def get_placement_outcomes_summary(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """University career-outcomes KPI: totals, trust mix, top employers, recents."""
    from app.modules.career_outcomes.application import read_service

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}
    try:
        kpi = await read_service.get_kpi(session, principal=principal, locale="en")
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    recent = [
        {
            "position": r.get("position_title"),
            "employer": r.get("employer_name"),
            "outcome": r.get("outcome"),
            "recorded_at": r.get("recorded_at"),
        }
        for r in (kpi.get("recent") or [])[:5]
    ]
    return {
        "ok": True,
        "total_outcomes": kpi.get("total_outcomes", 0),
        "by_trust_level": kpi.get("by_trust_level", []),
        "top_employers": kpi.get("top_employers", []),
        "recent": recent,
        "url": "/university/analytics/outcomes",
    }


async def analyze_attachment(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Analyse a file/image the staffer attached to THIS chat session.

    Read-only over the caller's OWN data: it loads an attachment the caller
    uploaded to their own session (owner + org scoped — a cross-user/cross-org id
    404s), runs the cost-tiered analysis cascade (native text -> OCR -> vision-LLM
    for images/scanned docs, reusing the extraction primitives) OFFLOADED off the
    event loop, and returns a compact, leakage-safe DATA ANALYSIS the assistant
    turns into tables + charts + a summary. Metered once per genuine analysis
    (the vision tier costs more); a re-analysis returns the cache free.

    Never returns the storage key/path, provider/model/token internals, or another
    user's/org's attachment. A non-analyzable/blank/junk file returns a clean
    "couldn't analyse" result — never a fabricated one.
    """
    from app.modules.ai_assistant.application import attachment_service

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}

    attachment_id = _parse_uuid(args.get("attachment_id"))
    if attachment_id is None:
        return {"ok": False, "error": "attachment_id_required"}

    try:
        result = await attachment_service.analyze_attachment(
            session, principal=principal, attachment_id=attachment_id
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    return {"ok": True, **result}


async def search_university_knowledge(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """RAG over the curated ``university`` institutional KB (+ shared platform KB).

    Prefers the dedicated ``university`` scope (institutional policies, handbooks,
    employer guidelines, career/moderation playbooks), unioned with ``platform``,
    via the shared hybrid retrieval + rerank + citation path (``tools.kb`` ->
    ``kb_service``). Scoping/authorization is delegated to
    ``get_kb_ids_for_query`` — a university KB is only ever returned for a member
    of the owning university org (or superadmin), never a student/partner/guest.

    Chunks are stripped to a leakage-safe shape before return: no chunk/kb/doc
    ids, no similarity scores, no provider/model internals — only the document
    title, section heading, and content the assistant needs to answer and cite.
    """
    from app.modules.ai_assistant.application.tools import kb
    from app.modules.knowledge_base.application import kb_service

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}
    result = await kb.knowledge_base_query(
        session, principal, args, scopes=kb_service.UNIVERSITY_QUERY_SCOPES
    )
    if result.get("ok"):
        result["chunks"] = _leakage_safe_chunks(result.get("chunks") or [])
    return result


async def start_operations_analysis(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Start a bounded, READ-ONLY multi-agent analysis of a partner's hiring quality.

    Delegates to the workforce facade, which RBAC-gates the run in the service
    layer (university-org staffer with ``partners:read``, or superadmin) and
    validates the target is a real partner org. Returns a run id the staffer polls
    via ``get_operations_analysis``. Advisory only — no consequential domain write.
    """
    from app.ai.agents import workforce

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}

    target_org_id = _parse_uuid(args.get("target_org_id"))
    if target_org_id is None:
        return {"ok": False, "error": "target_org_id_required"}
    target_type = (args.get("target_type") or "partner_hiring_quality").strip()

    try:
        data = await workforce.start_operations_analysis_run(
            session,
            principal=principal,
            target_org_id=target_org_id,
            target_type=target_type,
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except AppError:
        return {"ok": False, "error": "unsupported_target"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    return {
        "ok": True,
        "run_id": data["run_id"],
        "status": data["status"],
        "total_subtasks": data["total_subtasks"],
        "note": (
            "Analysis started in the background. Ask me to check it (with this run "
            "id) in a moment for the report. Advisory only — you decide any action."
        ),
    }


async def get_operations_analysis(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Poll a previously-started operations analysis and return the report if ready.

    Owner/org-scoped read (a run started by another org/user 404s). The returned
    ``summary`` is the synthesized, privacy-safe report (aggregates/bands only —
    no other-users' PII, no provider/model/token internals).
    """
    from app.ai.agents import workforce

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}

    run_id = _parse_uuid(args.get("run_id"))
    if run_id is None:
        return {"ok": False, "error": "run_id_required"}

    try:
        data = await workforce.get_operations_analysis_status(
            session, principal=principal, run_id=run_id
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    return {
        "ok": True,
        "status": data.get("status"),
        "total_passes": data.get("total_subtasks"),
        "completed_passes": data.get("completed_subtasks"),
        "report": data.get("summary"),
        "url": "/university/partners",
    }


def _leakage_safe_chunks(chunks: list[dict]) -> list[dict]:
    """Strip retrieval internals from KB chunks before they leave the tool.

    Keeps only ``document_title`` / ``section_heading`` / ``content`` (what the
    assistant needs to answer + let the §6.5 citation guard verify sources).
    Drops chunk id, kb id, document id, chunk index, token count, and any score —
    none of those may reach staff, and the assembled ``context`` string is
    already built from these same safe fields.
    """

    safe: list[dict] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        safe.append(
            {
                "document_title": chunk.get("document_title"),
                "section_heading": chunk.get("section_heading") or "",
                "content": chunk.get("content") or "",
            }
        )
    return safe


# --------------------------------------------------------------------------- #
# Write tools (confirmation-gated)                                             #
# --------------------------------------------------------------------------- #


async def approve_job_moderation(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Approve a pending job (publish it). Human-confirmed; fully audited.

    Delegates to ``moderation_service.approve_job`` — the same validator the
    university moderation UI's approve endpoint uses (org-type gate, transition
    guard, ``job.approved`` audit row, partner notification). No rule is
    duplicated here.
    """
    from app.modules.auth.application.context import RequestContext
    from app.modules.opportunities.application import moderation_service

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}

    job_id = _parse_uuid(args.get("job_id"))
    if job_id is None:
        return {"ok": False, "error": "job_id_required"}

    version_raw = args.get("version")
    version = version_raw if isinstance(version_raw, int) else None

    try:
        job = await moderation_service.approve_job(
            session,
            principal=principal,
            job_id=job_id,
            version=version,
            ctx=RequestContext(),
            locale="en",
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except AppError:
        return {"ok": False, "error": "not_approvable"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    return {
        "ok": True,
        "job_id": job.get("id"),
        "title": job.get("title"),
        "status": job.get("status_label") or job.get("status"),
        "url": "/university/moderation/jobs",
        "note": "Job approved and published. The posting partner has been notified.",
    }


async def request_job_changes(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Send a pending job back to the partner with a required reason.

    Maps to ``moderation_service.reject_job`` (the platform's send-back path):
    the job returns to the partner with the reason so they can revise and
    resubmit. Human-confirmed; audited (``job.rejected``); partner is notified.
    """
    from app.modules.auth.application.context import RequestContext
    from app.modules.opportunities.application import moderation_service

    if not _staff_ready(principal):
        return {"ok": False, "error": "university_auth_required"}

    job_id = _parse_uuid(args.get("job_id"))
    if job_id is None:
        return {"ok": False, "error": "job_id_required"}
    reason = (args.get("reason") or "").strip()
    if not reason:
        return {"ok": False, "error": "reason_required"}

    reason_code = (args.get("reason_code") or "").strip() or None
    version_raw = args.get("version")
    version = version_raw if isinstance(version_raw, int) else None

    try:
        job = await moderation_service.reject_job(
            session,
            principal=principal,
            job_id=job_id,
            reason=reason[:2000],
            reason_code=reason_code,
            version=version,
            ctx=RequestContext(),
            locale="en",
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except AppError:
        return {"ok": False, "error": "invalid_request"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    return {
        "ok": True,
        "job_id": job.get("id"),
        "title": job.get("title"),
        "status": job.get("status_label") or job.get("status"),
        "url": "/university/moderation/jobs",
        "note": "Job sent back with your reason. The posting partner has been notified.",
    }

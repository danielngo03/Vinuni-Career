"""Tool dispatch router — maps tool names to handler functions."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.application import ingestion_service as analytics
from app.shared.permissions import Principal, permission_checker

from . import companies, cv_ai, events, jobs, kb, partner, student, university
from .specs import (
    PARTNER_USER,
    STUDENT,
    TOOL_SPECS,
    UNIVERSITY_STAFF,
    ToolSpec,
)

SUPPORTED_TOOL_NAMES = frozenset(
    {
        "search_jobs",
        "get_job_detail",
        "get_job_alerts",
        "get_saved_jobs",
        "get_partner_jobs",
        "recommend_jobs",
        "save_job",
        "apply_job",
        "get_upcoming_events",
        "get_my_registered_events",
        "search_events",
        "get_my_applications",
        "get_profile_status",
        "get_upcoming_interviews",
        "search_companies",
        "get_company_detail",
        "get_company_reviews",
        "get_partner_pipeline_summary",
        "get_my_cvs",
        "get_skill_gap",
        "get_career_advice",
        "get_salary_benchmark",
        "start_interview_sim",
        "knowledge_base_query",
        "search_partner_candidates",
        "get_candidate_detail",
        "draft_job_description",
        "rewrite_job_description",
        "check_jd_bias",
        "suggest_scorecard",
        "generate_screening_brief",
        "get_upcoming_partner_events",
        "move_candidate_stage",
        # University staff operations tools
        "get_university_dashboard_summary",
        "get_moderation_queue",
        "get_pending_partner_registrations",
        "get_partner_overview",
        "get_at_risk_students",
        "get_cohort_summary",
        "get_career_services_report",
        "get_placement_outcomes_summary",
        "start_operations_analysis",
        "get_operations_analysis",
        "search_university_knowledge",
        "analyze_attachment",
        "approve_job_moderation",
        "request_job_changes",
    }
)


# --------------------------------------------------------------------------- #
# Central tool-RBAC gate (AI_PRODUCT_SPEC.md §2/§7; university control-plane   #
# P3/WS3.2). Enforced for EVERY persona before a tool executes — both in the  #
# read-only loop and the post-confirmation write path (both route through     #
# ``dispatch_tool``). The gate is defense-in-depth: each tool handler's        #
# underlying service still performs its own authoritative org-scoped check.    #
# --------------------------------------------------------------------------- #

# Map a real ``principal.persona`` string (student / partner_member /
# university_staff / alumni) to the ToolSpec ``persona`` FAMILY constant
# (STUDENT / PARTNER_USER / UNIVERSITY_STAFF). The ToolSpec family label
# "partner_user" intentionally differs from the real "partner_member" persona
# (see chat_service note), so the mapping cannot be an identity comparison.
_ROLE_TOKEN_FAMILIES = {
    "student": STUDENT,
    "alumni": STUDENT,
    "partner": PARTNER_USER,
    "partner_user": PARTNER_USER,
    "partner_member": PARTNER_USER,
    "university": UNIVERSITY_STAFF,
    "university_staff": UNIVERSITY_STAFF,
}


def _persona_family(principal: Principal) -> str | None:
    """Resolve the caller's ToolSpec persona family, or ``None`` if unknown."""

    persona = (principal.persona or "").lower()
    if persona in ("student", "alumni"):
        return STUDENT
    if persona.startswith("partner"):
        return PARTNER_USER
    if persona.startswith("university"):
        return UNIVERSITY_STAFF
    return None


def _satisfies_permission(token: str, principal: Principal, family: str | None) -> bool:
    """Resolve one ``required_permissions`` token against the caller.

    Vocabulary:
    - ``"authenticated"``            -> ``principal.is_authenticated``
    - ``"role:<persona-family>"``    -> the caller's persona family matches
      (``role:student`` / ``role:partner`` / ``role:partner_user`` /
      ``role:university_staff`` — normalised via ``_ROLE_TOKEN_FAMILIES``)
    - ``"<resource>:<action>"``      -> ``permission_checker.can(...)`` (catalog grant)
    An unrecognised token denies (fail closed).
    """

    if token == "authenticated":
        return principal.is_authenticated
    if token.startswith("role:"):
        want = _ROLE_TOKEN_FAMILIES.get(token[len("role:") :].strip().lower())
        return want is not None and family == want
    if ":" in token:
        resource, action = token.split(":", 1)
        return permission_checker.can(principal, resource, action)
    return False


def authorize_tool(spec: ToolSpec, principal: Principal) -> bool:
    """True if ``principal`` may invoke ``spec`` (persona family + grants).

    Superadmin passes everything. Otherwise BOTH must hold: (a) the tool's
    ``persona`` list includes the caller's persona family, and (b) every
    ``required_permissions`` token is satisfied.
    """

    if principal.is_superadmin:
        return True
    family = _persona_family(principal)
    if family is None or family not in spec.persona:
        return False
    return all(_satisfies_permission(tok, principal, family) for tok in spec.required_permissions)


async def dispatch_tool(
    name: str,
    args: dict,
    *,
    session: AsyncSession,
    principal: Principal,
) -> dict:
    """Execute a tool and return a structured result dict.

    Never raises — always returns ``{"ok": bool, ...}``.
    Callers must not surface raw error messages to end users.
    """
    valid, error = _validate_tool_args(name, args)
    if not valid:
        return {"ok": False, "error": error}

    # Central RBAC gate — deny (do NOT execute) when the caller's persona family
    # or catalog grants do not satisfy the tool's ``required_permissions``. Kept
    # as a structured, user-safe result (no internals) so the ReAct loop and the
    # confirmation path never crash on a raised exception (``dispatch_tool``
    # never raises, per its contract).
    spec = TOOL_SPECS[name]  # validated to exist by _validate_tool_args
    if not authorize_tool(spec, principal):
        result = {"ok": False, "error": "permission_denied"}
    else:
        result = await _execute_tool(name, args, session=session, principal=principal)
    # Metadata-only product-analytics fact (tool name + outcome, never prompt/
    # completion text or provider/model/token internals — those live in
    # ``ai_usage_log`` per .claude/rules/ai.md, a separate cost-tracking ledger).
    await analytics.record_event_safe(
        session,
        event_type="ai.tool.called",
        aggregate_type="ai_tool",
        aggregate_id=uuid.uuid4(),
        actor_id=principal.user_id if principal.is_authenticated else None,
        actor_type=_actor_type(principal),
        properties={"tool": name, "ok": bool(result.get("ok"))},
    )
    return result


def _actor_type(principal: Principal) -> str:
    """Normalize the persona string to the analytics ``actor_type`` vocabulary."""

    if not principal.is_authenticated:
        return "guest"
    if principal.persona.startswith("partner"):
        return "partner"
    if principal.persona.startswith("university"):
        return "university"
    if principal.persona == "student":
        return "student"
    return "system"


async def _execute_tool(
    name: str,
    args: dict,
    *,
    session: AsyncSession,
    principal: Principal,
) -> dict:
    try:
        # --- Job tools ---
        if name == "search_jobs":
            return await jobs.search_jobs(session, principal, args)
        if name == "get_job_detail":
            return await jobs.get_job_detail(session, principal, args)
        if name == "get_job_alerts":
            return await jobs.get_job_alerts(session, principal)
        if name == "get_saved_jobs":
            return await jobs.get_saved_jobs(session, principal)
        if name == "get_partner_jobs":
            return await jobs.get_partner_jobs(session, principal, args)
        if name == "recommend_jobs":
            return await jobs.recommend_jobs(session, principal, args)
        if name == "save_job":
            return await jobs.save_job(session, principal, args)
        if name == "apply_job":
            return await jobs.apply_job(session, principal, args)

        # --- Event tools ---
        if name == "get_upcoming_events":
            return await events.get_upcoming_events(session, principal, args)
        if name == "get_my_registered_events":
            return await events.get_my_registered_events(session, principal)
        if name == "search_events":
            return await events.search_events(session, principal, args)

        # --- Student tools ---
        if name == "get_my_applications":
            return await student.get_my_applications(session, principal)
        if name == "get_profile_status":
            return await student.get_profile_status(session, principal)
        if name == "get_upcoming_interviews":
            return await student.get_upcoming_interviews(session, principal)

        # --- Company tools ---
        if name == "search_companies":
            return await companies.search_companies(session, principal, args)
        if name == "get_company_detail":
            return await companies.get_company_detail(session, principal, args)
        if name == "get_company_reviews":
            return await companies.get_company_reviews(session, principal, args)

        # --- Partner tools ---
        if name == "get_partner_pipeline_summary":
            return await partner.get_partner_pipeline_summary(session, principal)
        if name == "search_partner_candidates":
            return await partner.search_partner_candidates(session, principal, args)
        if name == "get_candidate_detail":
            return await partner.get_candidate_detail(session, principal, args)
        if name == "draft_job_description":
            return await partner.draft_job_description(session, principal, args)
        if name == "rewrite_job_description":
            return await partner.rewrite_job_description(session, principal, args)
        if name == "check_jd_bias":
            return await partner.check_jd_bias(session, principal, args)
        if name == "suggest_scorecard":
            return await partner.suggest_scorecard(session, principal, args)
        if name == "generate_screening_brief":
            return await partner.generate_screening_brief(session, principal, args)
        if name == "get_upcoming_partner_events":
            return await partner.get_upcoming_partner_events(session, principal, args)
        if name == "move_candidate_stage":
            return await partner.move_candidate_stage(session, principal, args)

        # --- CV / AI tools ---
        if name == "get_my_cvs":
            return await cv_ai.get_my_cvs(session, principal)
        if name == "get_skill_gap":
            return await cv_ai.get_skill_gap(session, principal, args)
        if name == "get_career_advice":
            return await cv_ai.get_career_advice(session, principal, args)
        if name == "get_salary_benchmark":
            return await cv_ai.get_salary_benchmark(session, principal, args)
        if name == "start_interview_sim":
            return await cv_ai.start_interview_sim(session, principal, args)

        # --- Knowledge base ---
        if name == "knowledge_base_query":
            return await kb.knowledge_base_query(session, principal, args)

        # --- University staff operations tools ---
        if name == "get_university_dashboard_summary":
            return await university.get_university_dashboard_summary(session, principal, args)
        if name == "get_moderation_queue":
            return await university.get_moderation_queue(session, principal, args)
        if name == "get_pending_partner_registrations":
            return await university.get_pending_partner_registrations(session, principal, args)
        if name == "get_partner_overview":
            return await university.get_partner_overview(session, principal, args)
        if name == "get_at_risk_students":
            return await university.get_at_risk_students(session, principal, args)
        if name == "get_cohort_summary":
            return await university.get_cohort_summary(session, principal, args)
        if name == "get_career_services_report":
            return await university.get_career_services_report(session, principal, args)
        if name == "get_placement_outcomes_summary":
            return await university.get_placement_outcomes_summary(session, principal, args)
        if name == "start_operations_analysis":
            return await university.start_operations_analysis(session, principal, args)
        if name == "get_operations_analysis":
            return await university.get_operations_analysis(session, principal, args)
        if name == "search_university_knowledge":
            return await university.search_university_knowledge(session, principal, args)
        if name == "analyze_attachment":
            return await university.analyze_attachment(session, principal, args)
        if name == "approve_job_moderation":
            return await university.approve_job_moderation(session, principal, args)
        if name == "request_job_changes":
            return await university.request_job_changes(session, principal, args)

        return {"ok": False, "error": "unknown_tool"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}


def _validate_tool_args(name: str, args: dict) -> tuple[bool, str | None]:
    spec = TOOL_SPECS.get(name)
    if spec is None:
        return False, "unknown_tool"
    if not isinstance(args, dict):
        return False, "invalid_args"

    schema = spec.parameters or {}
    required = schema.get("required") or []
    for key in required:
        if args.get(key) in (None, ""):
            return False, f"missing_{key}"

    properties = schema.get("properties") or {}
    for key, value in args.items():
        expected = (properties.get(key) or {}).get("type")
        if value is None or expected is None:
            continue
        if expected == "string" and not isinstance(value, str):
            return False, f"invalid_{key}"
        if expected == "integer" and not isinstance(value, int):
            return False, f"invalid_{key}"
        if expected == "object" and not isinstance(value, dict):
            return False, f"invalid_{key}"

    return True, None

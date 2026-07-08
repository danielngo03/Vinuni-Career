"""Tool dispatch router — maps tool names to handler functions."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.application import ingestion_service as analytics
from app.shared.permissions import Principal, permission_checker

from . import companies, cv_ai, events, jobs, kb, partner, student
from .specs import PARTNER_USER, STUDENT, TOOL_SPECS, UNIVERSITY_STAFF, ToolSpec

# Map the auth-layer persona (``Principal.persona``, e.g. "partner_member")
# to the ``ToolSpec.persona`` vocabulary declared in ``specs.py`` (STUDENT /
# PARTNER_USER / UNIVERSITY_STAFF). Alumni reuse the student tool surface;
# guests never reach dispatch (chat_service raises AuthRequiredError first) and
# map to no tool persona (so every persona-scoped tool is rejected for them).
_AUTH_PERSONA_TO_TOOL_PERSONA: dict[str, str] = {
    "student": STUDENT,
    "alumni": STUDENT,
    "partner_member": PARTNER_USER,
    "university_staff": UNIVERSITY_STAFF,
}

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
        "get_partner_analytics_summary",
        "move_candidate_stage",
        "analyze_attachment",
    }
)


def _tool_not_permitted(principal: Principal, spec: ToolSpec) -> bool:
    """Persona + capability gate at the dispatch boundary (defense-in-depth).

    Returns ``True`` when ``principal`` may NOT dispatch ``spec``. This runs
    before EVERY tool execution path (read-only ReAct loop, deterministic plan
    execution, and post-confirmation execution all go through ``dispatch_tool``)
    so a partner can never dispatch a student-only tool (and vice-versa) even if
    a jailbroken model or a mis-routed plan requests it. It COMPLEMENTS — never
    replaces — the org-scoped ownership RBAC each tool handler already enforces.

    - Persona: map the auth persona to the ``ToolSpec.persona`` vocabulary and
      require it to be in the tool's declared persona list.
    - Capabilities: enforce ``ToolSpec.required_permissions``. ``authenticated``
      maps to ``is_authenticated``; ``role:<p>`` must agree with the mapped tool
      persona; any ``resource:action`` capability is checked via
      ``permission_checker`` (dormant for the current tool set, correct for
      future tools).
    """
    tool_persona = _AUTH_PERSONA_TO_TOOL_PERSONA.get(principal.persona)
    if tool_persona is None or tool_persona not in spec.persona:
        return True
    for perm in spec.required_permissions:
        if perm == "authenticated":
            if not principal.is_authenticated:
                return True
            continue
        if perm.startswith("role:"):
            if perm.split(":", 1)[1] != tool_persona:
                return True
            continue
        resource_type, _, action = perm.partition(":")
        if action and not permission_checker.can(principal, resource_type, action):
            return True
    return False


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
    spec = TOOL_SPECS.get(name)
    if spec is None:
        return {"ok": False, "error": "unknown_tool"}
    if _tool_not_permitted(principal, spec):
        # Persona/capability mismatch — do NOT execute, do NOT record an
        # analytics fact (mirrors the early-return arg-validation behaviour).
        return {"ok": False, "error": "tool_not_permitted"}

    valid, error = _validate_tool_args(name, args)
    if not valid:
        return {"ok": False, "error": error}

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
        if name == "get_partner_analytics_summary":
            return await partner.get_partner_analytics_summary(session, principal)
        if name == "move_candidate_stage":
            return await partner.move_candidate_stage(session, principal, args)
        if name == "analyze_attachment":
            return await partner.analyze_attachment(session, principal, args)

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

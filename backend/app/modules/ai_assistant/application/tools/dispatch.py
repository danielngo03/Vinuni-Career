"""Tool dispatch router — maps tool names to handler functions.

Dispatch is a ``dict[str, Handler]`` registry (``_TOOL_HANDLERS``) rather than a
long ``if name == ...`` chain. Every ``TOOL_SPECS`` entry must have exactly one
handler and vice-versa — this is asserted at import time (``_assert_registry_complete``),
mirroring how ``ToolSpec.__post_init__`` enforces its own §7 invariants, so a new
spec or handler cannot ship half-wired.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.application import ingestion_service as analytics
from app.shared import personas
from app.shared.permissions import Principal, permission_checker

from . import companies, cv_ai, events, jobs, kb, partner, student
from .specs import PARTNER_USER, STUDENT, TOOL_SPECS, UNIVERSITY_STAFF, ToolSpec

# Map the auth-layer persona (``Principal.persona``, e.g. "partner_member") to
# the ``ToolSpec.persona`` vocabulary declared in ``specs.py`` (STUDENT /
# PARTNER_USER / UNIVERSITY_STAFF). Persona strings come from the shared kernel
# (``app.shared.personas``) so this defensive map cannot drift from the persona
# registry that drives prompt/planner selection. Alumni reuse the student tool
# surface; guests never reach dispatch (chat_service raises AuthRequiredError
# first) and map to no tool persona (so every persona-scoped tool is rejected
# for them). This module must NOT import the agentic persona registry — the
# prompts it imports would create a tool ↔ prompt import cycle — so it keeps its
# own map, sharing only the string constants.
_AUTH_PERSONA_TO_TOOL_PERSONA: dict[str, str] = {
    personas.STUDENT: STUDENT,
    personas.ALUMNI: STUDENT,
    personas.PARTNER_MEMBER: PARTNER_USER,
    personas.UNIVERSITY_STAFF: UNIVERSITY_STAFF,
}

# Tool name -> handler. Handlers are ``(session, principal, args) -> dict``;
# handlers that ignore ``args`` are adapted with a thin lambda so the registry
# has one uniform call shape. This is the single source of truth for what
# ``_execute_tool`` can dispatch — kept in lockstep with ``TOOL_SPECS`` by the
# import-time completeness check below.
_ToolHandler = Callable[[AsyncSession, Principal, dict], Awaitable[dict]]

_TOOL_HANDLERS: dict[str, _ToolHandler] = {
    # --- Job tools ---
    "search_jobs": jobs.search_jobs,
    "get_job_detail": jobs.get_job_detail,
    "get_job_alerts": lambda s, p, _a: jobs.get_job_alerts(s, p),
    "get_saved_jobs": lambda s, p, _a: jobs.get_saved_jobs(s, p),
    "get_partner_jobs": jobs.get_partner_jobs,
    "recommend_jobs": jobs.recommend_jobs,
    "save_job": jobs.save_job,
    "apply_job": jobs.apply_job,
    # --- Event tools ---
    "get_upcoming_events": events.get_upcoming_events,
    "get_my_registered_events": lambda s, p, _a: events.get_my_registered_events(s, p),
    "search_events": events.search_events,
    # --- Student tools ---
    "get_my_applications": lambda s, p, _a: student.get_my_applications(s, p),
    "get_profile_status": lambda s, p, _a: student.get_profile_status(s, p),
    "get_upcoming_interviews": lambda s, p, _a: student.get_upcoming_interviews(s, p),
    # --- Company tools ---
    "search_companies": companies.search_companies,
    "get_company_detail": companies.get_company_detail,
    "get_company_reviews": companies.get_company_reviews,
    # --- Partner tools ---
    "get_partner_pipeline_summary": lambda s, p, _a: partner.get_partner_pipeline_summary(s, p),
    "search_partner_candidates": partner.search_partner_candidates,
    "get_candidate_detail": partner.get_candidate_detail,
    "draft_job_description": partner.draft_job_description,
    "rewrite_job_description": partner.rewrite_job_description,
    "check_jd_bias": partner.check_jd_bias,
    "suggest_scorecard": partner.suggest_scorecard,
    "generate_screening_brief": partner.generate_screening_brief,
    "get_upcoming_partner_events": partner.get_upcoming_partner_events,
    "get_partner_analytics_summary": lambda s, p, _a: partner.get_partner_analytics_summary(s, p),
    "move_candidate_stage": partner.move_candidate_stage,
    "analyze_attachment": partner.analyze_attachment,
    # --- CV / AI tools ---
    "get_my_cvs": lambda s, p, _a: cv_ai.get_my_cvs(s, p),
    "get_skill_gap": cv_ai.get_skill_gap,
    "get_career_advice": cv_ai.get_career_advice,
    "get_salary_benchmark": cv_ai.get_salary_benchmark,
    "start_interview_sim": cv_ai.start_interview_sim,
    # --- Knowledge base ---
    "knowledge_base_query": kb.knowledge_base_query,
}


def _assert_registry_complete() -> None:
    """Fail fast at import if specs and handlers drift out of lockstep (§7).

    Every ``TOOL_SPECS`` entry must have a dispatch handler and every handler
    must have a spec — an orphan on either side is a wiring bug, not a runtime
    "unknown tool" the model should ever see.
    """
    spec_names = set(TOOL_SPECS)
    handler_names = set(_TOOL_HANDLERS)
    missing = spec_names - handler_names
    orphan = handler_names - spec_names
    if missing:
        raise RuntimeError(f"Tool specs without a dispatch handler: {sorted(missing)}")
    if orphan:
        raise RuntimeError(f"Dispatch handlers without a tool spec: {sorted(orphan)}")


_assert_registry_complete()


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
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "error": "unknown_tool"}
    try:
        return await handler(session, principal, args)
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

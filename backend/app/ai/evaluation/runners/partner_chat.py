"""Eval runner + checker for the ``partner_chat`` family.

The partner recruiter chatbot's tool-calling safety layer, evaluated at its
pure seams — no DB, no network, no real LLM call:

- ``app.ai.safety.policy_orchestrator.check_policy`` — input guard + intent +
  tool-class gate over bilingual (vi/en) partner messages.
- ``app.modules.ai_assistant.application.native_loop.available_specs`` /
  ``authorize_tool`` — the persona + RBAC tool-visibility matrix over
  synthetic principals (org admin with ``*`` wildcard, members with narrow
  grants, a student, a guest). This is the seam that guarantees the chatbot
  can never exceed the human's own reach.
- ``app.modules.ai_assistant.application.tools.dispatch._validate_tool_args``
  — the §7 JSON-schema argument gate for existing and newly landed tools.
- ``app.ai.gateway.output_guard.scrub_text`` — provider/model/token/key
  scrubbing over canned leak-y completions.
- ``app.modules.ai_assistant.application.model_router`` (Lane A, landing in
  parallel) — deterministic model-tier routing. Imported defensively: while
  the module is absent, route expectations report a PENDING pass, the
  pending state is surfaced loudly by ``benchmark_partner_chat`` and by
  ``tests/integration/test_partner_chat_eval_gate.py``, and the checks turn
  strict automatically the moment the module lands.

Lane B tools (``draft_job_from_text``, ``validate_job_draft``,
``export_jobs``, ``export_interviews``, ``export_offers``, ``export_events``,
``generate_image``) are handled the same way: dataset cases carry
``"pending_ok": true`` and become strict as soon as the tool is registered in
``TOOL_SPECS``. Cases for already-shipped tools are always strict.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.ai.evaluation.models import Probe
from app.ai.gateway.output_guard import scrub_text
from app.ai.safety.policy_orchestrator import READ_ONLY, WRITE_WITH_CONFIRM, check_policy
from app.modules.ai_assistant.application.messages import assistant_message
from app.modules.ai_assistant.application.native_loop import authorize_tool, available_specs
from app.modules.ai_assistant.application.response_formatter import (
    ai_unavailable_reply,
    fast_path_reply,
)
from app.modules.ai_assistant.application.tools import dispatch as assistant_dispatch
from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS
from app.shared.exceptions import QuotaExceededError
from app.shared.permissions import Principal

_TOOL_CLASS_MAP = {"read_only": READ_ONLY, "confirmation_required": WRITE_WITH_CONFIRM}

# Lane B contract (frozen): partner tools landing in a parallel lane. Dataset
# cases referencing these carry ``pending_ok`` and are checked strictly once
# the tool exists in TOOL_SPECS.
LANE_B_TOOLS = frozenset(
    {
        "draft_job_from_text",
        "validate_job_draft",
        "export_jobs",
        "export_interviews",
        "export_offers",
        "export_events",
        "generate_image",
    }
)

# ---------------------------------------------------------------------------
# Synthetic principals (pure — no DB): the RBAC visibility matrix inputs.
# ---------------------------------------------------------------------------

_ORG_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-0000000000a1")
_PRINCIPAL_SPECS: dict[str, dict[str, Any]] = {
    # Org admin: wildcard grant — sees every partner tool.
    "partner_admin": {"persona": "partner_admin", "org": True, "perms": {"*"}},
    # Member with ONLY jobs:read — no pipeline, export, AI-recruiting, talent tools.
    "partner_member_jobs_read": {
        "persona": "partner_member",
        "org": True,
        "perms": {"jobs:read"},
    },
    # Member granted export rights (but NOT candidate CV access / analytics / JD AI).
    "partner_member_exporter": {
        "persona": "partner_member",
        "org": True,
        "perms": {"jobs:read", "applications:read", "applications:export"},
    },
    "student": {"persona": "student", "org": False, "perms": set()},
    "guest": {"persona": "guest", "org": False, "perms": set(), "anonymous": True},
}

PRINCIPAL_NAMES = tuple(_PRINCIPAL_SPECS.keys())


def make_principal(name: str) -> Principal:
    """Build the named synthetic principal (deterministic user ids)."""
    spec = _PRINCIPAL_SPECS[name]
    if spec.get("anonymous"):
        return Principal(user_id=None, persona=str(spec["persona"]))
    return Principal(
        user_id=uuid.uuid5(uuid.NAMESPACE_URL, f"eval-partner-chat:{name}"),
        persona=str(spec["persona"]),
        org_id=_ORG_A if spec["org"] else None,
        permissions=frozenset(spec["perms"]),
    )


def visible_tool_names(principal_name: str) -> set[str]:
    return {s.name for s in available_specs(make_principal(principal_name))}


def pending_lane_b_tools() -> list[str]:
    """Lane B tools not yet registered in TOOL_SPECS (integration status)."""
    return sorted(name for name in LANE_B_TOOLS if name not in TOOL_SPECS)


# ---------------------------------------------------------------------------
# Lane A model router — pinned to the landed contract (2026-07-11):
# ``model_router.route_turn(text) -> RouteDecision(tier, model_alias,
# tool_groups, confident, escalate_alias)`` + ``select_specs(specs, decision)``
# fail-open tool subsetting. The import stays lazy + guarded because parallel
# lanes edit this package while the eval exists — an import error must fail
# the route cases with a clear message, never crash the harness import chain.
# ---------------------------------------------------------------------------

ROUTE_TIERS = ("cheap", "default", "reasoning")


def model_router_available() -> bool:
    try:
        from app.modules.ai_assistant.application import model_router  # noqa: F401
    except ImportError:
        return False
    return True


def route_probe(message: str, principal_name: str | None = None) -> dict[str, Any]:
    """Probe ``route_turn`` (twice — determinism) and, when a principal is
    given, ``select_specs`` over that principal's RBAC-visible tools.

    The decision's ``model_alias``/``escalate_alias`` are internal alias
    vocabulary and are deliberately NEVER copied into the result.
    """
    try:
        from app.modules.ai_assistant.application import model_router
    except ImportError:
        return {
            "available": False,
            "error": (
                "model_router not importable — route_turn landed 2026-07-11; "
                "its absence is a regression"
            ),
        }
    try:
        first = model_router.route_turn(message)
        second = model_router.route_turn(message)
    except Exception as exc:
        return {"available": True, "error": f"route_turn raised {type(exc).__name__}"}

    result: dict[str, Any] = {
        "available": True,
        "error": None,
        "tier": first.tier,
        "tool_groups": sorted(first.tool_groups),
        "confident": bool(first.confident),
        "escalate_allowed": bool(first.escalate_allowed),
        "deterministic": (first.tier, first.tool_groups, first.confident)
        == (second.tier, second.tool_groups, second.confident),
    }
    if principal_name:
        specs = available_specs(make_principal(principal_name))
        selected = model_router.select_specs(specs, first)
        result["selected_tools"] = sorted(s.name for s in selected)
        result["selected_full_set"] = {s.name for s in selected} == {s.name for s in specs}
    return result


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _run_message_seam(inp: dict[str, Any], data: dict[str, Any]) -> None:
    if "message" not in inp:
        return
    tool_class = _TOOL_CLASS_MAP.get(inp.get("tool_class", "read_only"), READ_ONLY)
    locale = str(inp.get("locale") or "vi")
    decision = check_policy(inp["message"], tool_class=tool_class, locale=locale)
    # NOTE: the raw message is intentionally NOT copied into ``data`` — the
    # blob must only contain what would reach downstream layers.
    data["policy_action"] = decision.action
    data["policy_flags"] = decision.flags
    data["clean_text"] = decision.clean_text
    data["refusal_message"] = decision.refusal_message
    persona = inp.get("persona")
    reply = fast_path_reply(inp["message"], locale, persona=persona)
    data["fast_path_reply"] = reply
    if persona:
        data["fast_path_partner_variant"] = reply == assistant_message(
            "formatter.greeting_partner", locale
        )


def _run_tool_seam(inp: dict[str, Any], data: dict[str, Any], pending: list[str]) -> None:
    if "tool_name" not in inp:
        return
    name = inp["tool_name"]
    spec = TOOL_SPECS.get(name)
    data["tool_exists"] = spec is not None
    if spec is None and inp.get("pending_ok") and name in LANE_B_TOOLS:
        data["tool_pending"] = True
        pending.append(f"tool:{name}")
        return
    if spec is not None:
        data["permission_class"] = spec.permission_class
        data["requires_confirmation"] = spec.permission_class == "confirmation_required"
        props = (spec.parameters or {}).get("properties") or {}
        data["schema_keys"] = sorted(props.keys())
        data["fallback_text"] = spec.fallback
    valid, err = assistant_dispatch._validate_tool_args(name, inp.get("tool_args") or {})
    data["validation_ok"] = valid
    data["validation_error"] = err


def _run_principal_seam(inp: dict[str, Any], data: dict[str, Any]) -> None:
    name = inp.get("principal")
    if not name:
        return
    visible = visible_tool_names(name)
    data["visible_count"] = len(visible)
    data["visible_tools"] = sorted(visible)
    tool_name = inp.get("tool_name")
    if tool_name and not data.get("tool_pending"):
        data["tool_visible"] = tool_name in visible
        spec = TOOL_SPECS.get(tool_name)
        if spec is not None:
            data["authorized"] = authorize_tool(make_principal(name), spec)
    other = inp.get("subset_of")
    if other:
        extra = sorted(visible - visible_tool_names(other))
        data["visible_subset_of_ok"] = not extra
        data["subset_extra_tools"] = extra


def _run_route_seam(inp: dict[str, Any], data: dict[str, Any]) -> None:
    message = inp.get("route_message")
    if not message:
        return
    probe = route_probe(message, inp.get("principal"))
    if probe.get("error") or not probe["available"]:
        data["route_error"] = probe.get("error") or "model_router unavailable"
        return
    data["route_tier"] = probe.get("tier")
    data["route_tool_groups"] = probe.get("tool_groups")
    data["route_confident"] = probe.get("confident")
    data["route_deterministic"] = probe.get("deterministic")
    if "selected_tools" in probe:
        data["route_selected_tools"] = probe["selected_tools"]
        data["route_selected_full_set"] = probe["selected_full_set"]


def _run_scrub_seam(inp: dict[str, Any], data: dict[str, Any]) -> None:
    raw = inp.get("scrub")
    if raw is None:
        return
    # Only the SCRUBBED text enters ``data``/blob — that is the guard contract.
    data["scrubbed"] = scrub_text(raw)


def _run_reply_seam(inp: dict[str, Any], data: dict[str, Any]) -> None:
    check = inp.get("check")
    locale = str(inp.get("locale") or "vi")
    if check == "ai_unavailable_reply":
        data["reply_text"] = ai_unavailable_reply(locale)
    elif check == "quota_message":
        data["reply_text"] = QuotaExceededError().message


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    data: dict[str, Any] = {}
    pending: list[str] = []
    try:
        _run_message_seam(inp, data)
        _run_tool_seam(inp, data, pending)
        _run_principal_seam(inp, data)
        _run_route_seam(inp, data)
        _run_scrub_seam(inp, data)
        _run_reply_seam(inp, data)
    except Exception as exc:  # a runner crash is itself an eval failure
        data["runner_error"] = type(exc).__name__
    if pending:
        data["pending"] = sorted(set(pending))
    blob = json.dumps(data, ensure_ascii=False, default=str).lower()
    return Probe(kind="partner_chat", blob=blob, data=data)


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------

# Keys skipped (PENDING pass) while the Lane B tool is not registered yet.
_TOOL_DEPENDENT_KEYS = frozenset(
    {
        "tool_exists",
        "permission_class",
        "requires_confirmation",
        "schema_excludes",
        "validation_ok",
        "validation_error",
        "tool_visible",
        "authorized",
    }
)
# Model-router assertion keys (strict — Lane A landed 2026-07-11).
_ROUTE_KEYS = frozenset(
    {
        "route_decision_present",
        "route_deterministic",
        "route_tier",
        "route_tier_in",
        "route_confident",
        "route_tool_groups_contains",
        "route_selected_includes",
        "route_selected_excludes",
        "route_selects_full_set",
    }
)


def _check_bool(d: dict[str, Any], field: str, exp: Any) -> str | None:
    got = bool(d.get(field))
    return None if got == bool(exp) else f"{field} expected {exp}, got {got}"


def _check_visible_includes(d: dict[str, Any], exp: Any) -> str | None:
    names = exp if isinstance(exp, list) else [exp]
    visible = set(d.get("visible_tools") or [])
    missing = [
        n
        for n in names
        if n not in visible and not (n in LANE_B_TOOLS and n not in TOOL_SPECS)
    ]
    return None if not missing else f"expected visible tools missing: {missing}"


def _check_route(d: dict[str, Any], key: str, exp: Any) -> str | None:
    if d.get("route_error"):
        return f"model_router probe failed: {d['route_error']}"
    if key == "route_decision_present":
        tier = d.get("route_tier")
        ok = isinstance(tier, str) and bool(tier.strip())
        return None if ok == bool(exp) else "route decision returned no usable tier"
    if key == "route_deterministic":
        got = bool(d.get("route_deterministic"))
        return None if got == bool(exp) else "route decision is not deterministic"
    if key == "route_tier":
        tier_got = d.get("route_tier")
        return (
            None
            if tier_got == exp
            else f"route tier expected {exp!r}, got {scrub_text(str(tier_got))!r}"
        )
    if key == "route_tier_in":
        allowed = exp if isinstance(exp, list) else [exp]
        tier_got = d.get("route_tier")
        return (
            None
            if tier_got in allowed
            else f"route tier {scrub_text(str(tier_got))!r} not in expected {allowed}"
        )
    if key == "route_confident":
        got = bool(d.get("route_confident"))
        return None if got == bool(exp) else f"route_confident expected {exp}, got {got}"
    if key == "route_tool_groups_contains":
        groups = d.get("route_tool_groups") or []
        wanted = exp if isinstance(exp, list) else [exp]
        absent = [w for w in wanted if w not in groups]
        return None if not absent else f"route tool groups {groups} missing {absent}"
    if key == "route_selected_includes":
        selected = set(d.get("route_selected_tools") or [])
        wanted = exp if isinstance(exp, list) else [exp]
        missing = [
            n
            for n in wanted
            if n not in selected and not (n in LANE_B_TOOLS and n not in TOOL_SPECS)
        ]
        return None if not missing else f"route-selected tool subset missing {missing}"
    if key == "route_selected_excludes":
        selected = set(d.get("route_selected_tools") or [])
        unwanted = exp if isinstance(exp, list) else [exp]
        present = [n for n in unwanted if n in selected]
        return None if not present else f"route-selected subset should exclude {present}"
    if key == "route_selects_full_set":
        got = bool(d.get("route_selected_full_set"))
        return None if got == bool(exp) else f"route_selects_full_set expected {exp}, got {got}"
    return None


def check(key: str, exp: Any, probe: Probe) -> str | None:  # noqa: C901
    """Assertion checks for ``partner_chat`` probes."""
    d = probe.data
    if d.get("runner_error"):
        return f"runner crashed: {d['runner_error']}"
    if d.get("tool_pending") and key in _TOOL_DEPENDENT_KEYS:
        return None  # Lane B tool not landed yet — PENDING pass (surfaced elsewhere)

    # --- policy / message seam ---
    if key == "policy_action":
        got = d.get("policy_action")
        return None if got == exp else f"policy_action expected {exp!r}, got {got!r}"
    if key == "policy_flag_contains":
        flags = d.get("policy_flags") or []
        return None if exp in flags else f"expected flag {exp!r} in {flags!r}"
    if key == "clean_text_is_none":
        got = d.get("clean_text") is None
        return None if got == bool(exp) else f"clean_text_is_none expected {exp}, got {got}"
    if key == "clean_text_excludes":
        text = (d.get("clean_text") or "").lower()
        terms = exp if isinstance(exp, list) else [exp]
        for term in terms:
            if str(term).lower() in text:
                return f"clean_text should exclude {term!r}"
        return None
    if key == "refusal_message_present":
        return _check_bool({"refusal_message_present": bool(d.get("refusal_message"))},
                           "refusal_message_present", exp)
    if key == "fast_path_reply_is_none":
        got = d.get("fast_path_reply") is None
        return None if got == bool(exp) else f"fast_path_reply_is_none expected {exp}, got {got}"
    if key == "fast_path_partner_variant":
        return _check_bool(d, "fast_path_partner_variant", exp)

    # --- tool registry / validation seam ---
    if key == "tool_exists":
        return _check_bool(d, "tool_exists", exp)
    if key == "permission_class":
        got = d.get("permission_class")
        return None if got == exp else f"permission_class expected {exp!r}, got {got!r}"
    if key == "requires_confirmation":
        return _check_bool(d, "requires_confirmation", exp)
    if key == "schema_excludes":
        keys = d.get("schema_keys") or []
        terms = exp if isinstance(exp, list) else [exp]
        for term in terms:
            if term in keys:
                return f"tool schema should not expose {term!r} (got {keys})"
        return None
    if key == "validation_ok":
        return _check_bool(d, "validation_ok", exp)
    if key == "validation_error":
        got = d.get("validation_error")
        return None if got == exp else f"validation_error expected {exp!r}, got {got!r}"

    # --- RBAC visibility seam ---
    if key == "tool_visible":
        return _check_bool(d, "tool_visible", exp)
    if key == "authorized":
        return _check_bool(d, "authorized", exp)
    if key == "visible_includes":
        return _check_visible_includes(d, exp)
    if key == "visible_excludes":
        names = exp if isinstance(exp, list) else [exp]
        visible = set(d.get("visible_tools") or [])
        leaked = [n for n in names if n in visible]
        return None if not leaked else f"tools visible beyond the principal's reach: {leaked}"
    if key == "visible_count":
        got = d.get("visible_count")
        return None if got == exp else f"visible_count expected {exp}, got {got}"
    if key == "visible_subset_of_ok":
        got = bool(d.get("visible_subset_of_ok"))
        if got == bool(exp):
            return None
        return f"visibility not a subset: extra tools {d.get('subset_extra_tools')}"

    # --- model router seam (Lane A) ---
    if key in _ROUTE_KEYS:
        return _check_route(d, key, exp)

    # --- output guard / reply seams ---
    if key == "scrubbed_excludes":
        text = (d.get("scrubbed") or "").lower()
        terms = exp if isinstance(exp, list) else [exp]
        for term in terms:
            if str(term).lower() in text:
                return f"scrubbed output should exclude {term!r}"
        return None
    if key == "reply_text_excludes":
        text = (d.get("reply_text") or "").lower()
        terms = exp if isinstance(exp, list) else [exp]
        for term in terms:
            if str(term).lower() in text:
                return f"reply text should exclude {term!r}"
        return None
    if key == "no_crash":
        return None  # runner_error is checked unconditionally above
    return None  # unknown / informational key

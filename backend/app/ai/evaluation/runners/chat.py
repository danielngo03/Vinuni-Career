"""Eval runner + checker for the ``ai_assistant_chat`` family.

The ReAct tool-calling safety layer shared by every assistant tool: the
policy orchestrator (input guard + intent + tool-class gate), the LLM
tool-call JSON parser, and the tool registry §7 contract (permission class,
schema, fallback text). Pure functions only — no DB, no principal, no
network. See AI_PRODUCT_SPEC.md §4.1, §7, §9.1.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.evaluation.models import Probe
from app.ai.safety.policy_orchestrator import READ_ONLY, WRITE_WITH_CONFIRM, check_policy
from app.modules.ai_assistant.application.response_formatter import (
    ai_unavailable_reply,
    fast_path_reply,
    strip_tool_call_json,
)
from app.modules.ai_assistant.application.tool_loop import parse_tool_call
from app.modules.ai_assistant.application.tools import dispatch as assistant_dispatch
from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS

_CHAT_TOOL_CLASS_MAP = {"read_only": READ_ONLY, "confirmation_required": WRITE_WITH_CONFIRM}


async def run_case(case: dict[str, Any]) -> Probe:  # noqa: C901
    inp = case.get("input") or {}
    data: dict[str, Any] = {}

    if "message" in inp:
        tool_class = _CHAT_TOOL_CLASS_MAP.get(inp.get("tool_class", "read_only"), READ_ONLY)
        decision = check_policy(inp["message"], tool_class=tool_class)
        data["policy_action"] = decision.action
        data["policy_flags"] = decision.flags
        data["clean_text"] = decision.clean_text
        data["refusal_message"] = decision.refusal_message
        data["fast_path_reply"] = fast_path_reply(inp["message"])

    if "raw_llm_output" in inp:
        parsed = parse_tool_call(inp["raw_llm_output"])
        data["parsed_tool_call"] = parsed
        data["stripped_text"] = strip_tool_call_json(inp["raw_llm_output"])
        if parsed:
            data["parsed_tool_exists"] = parsed.get("name") in TOOL_SPECS

    if "tool_name" in inp:
        tool_name = inp["tool_name"]
        spec = TOOL_SPECS.get(tool_name)
        data["tool_exists"] = spec is not None
        if spec is not None:
            data["permission_class"] = spec.permission_class
            data["requires_confirmation"] = spec.permission_class == "confirmation_required"
            props = (spec.parameters or {}).get("properties") or {}
            data["schema_keys"] = sorted(props.keys())
            data["fallback_text"] = spec.fallback
        tool_args = inp.get("tool_args", {})
        valid, err = assistant_dispatch._validate_tool_args(tool_name, tool_args)
        data["validation_ok"] = valid
        data["validation_error"] = err

    if inp.get("check") == "ai_unavailable_reply":
        data["reply_text"] = ai_unavailable_reply()

    blob = json.dumps(data, ensure_ascii=False, default=str).lower()
    return Probe(kind="chat", blob=blob, data=data)


def check(key: str, exp: Any, probe: Probe) -> str | None:  # noqa: C901
    """Assertion checks for ``ai_assistant_chat`` probes (policy + tool registry)."""
    d = probe.data
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
        return None if str(exp).lower() not in text else f"clean_text should exclude {exp!r}"
    if key == "refusal_message_present":
        got = bool(d.get("refusal_message"))
        return None if got == bool(exp) else f"refusal_message_present expected {exp}, got {got}"
    if key == "fast_path_reply_is_none":
        got = d.get("fast_path_reply") is None
        return None if got == bool(exp) else f"fast_path_reply_is_none expected {exp}, got {got}"
    if key == "reply_text_excludes":
        text = (d.get("reply_text") or "").lower()
        return None if str(exp).lower() not in text else f"reply_text should exclude {exp!r}"
    if key == "tool_exists":
        got = bool(d.get("tool_exists"))
        return None if got == bool(exp) else f"tool_exists expected {exp}, got {got}"
    if key == "permission_class":
        got = d.get("permission_class")
        return None if got == exp else f"permission_class expected {exp!r}, got {got!r}"
    if key == "requires_confirmation":
        got = bool(d.get("requires_confirmation"))
        return None if got == bool(exp) else f"requires_confirmation expected {exp}, got {got}"
    if key == "schema_excludes":
        keys = d.get("schema_keys") or []
        return None if exp not in keys else f"tool schema should not expose {exp!r} (got {keys})"
    if key == "validation_ok":
        got = bool(d.get("validation_ok"))
        return None if got == bool(exp) else f"validation_ok expected {exp}, got {got}"
    if key == "validation_error":
        got = d.get("validation_error")
        return None if got == exp else f"validation_error expected {exp!r}, got {got!r}"
    if key == "parsed_tool_call_name":
        got = (d.get("parsed_tool_call") or {}).get("name")
        return None if got == exp else f"parsed tool_call name expected {exp!r}, got {got!r}"
    if key == "parsed_role_arg":
        got = (d.get("parsed_tool_call") or {}).get("args", {}).get("role")
        return None if got == exp else f"parsed tool_call args.role expected {exp!r}, got {got!r}"
    if key == "parsed_tool_exists_for_parsed":
        got = bool(d.get("parsed_tool_exists"))
        return None if got == bool(exp) else (
            f"parsed_tool_exists_for_parsed expected {exp}, got {got}"
        )
    if key == "no_crash":
        return None
    return None  # unknown / informational key

"""Eval runner + checker for the ``student_rag`` family.

Knowledge-base RAG **grounding + injection defense** for the STUDENT career
assistant, evaluated at real, deterministic seams — no DB, no network, no model
call. The student mirror of ``partner_rag``:

- ``app.ai.retrieval.citation_verify.verify_citations`` (§6.5) — the
  post-generation safety net: every ``Theo <Doc>`` / ``According to <Doc>``
  citation in a career-advice answer must name a document that was ACTUALLY
  retrieved this turn; an ungrounded citation (a fabricated handbook, a made-up
  blog, another org's internal doc) is stripped + flagged as a hallucination
  risk. This is how "answer cites the doc / honest not-enough-info" is enforced
  offline.
- ``app.ai.safety.input_guard.neutralize_untrusted_text`` — a poisoned KB chunk
  (injection embedded in retrieved career text) is defused before it re-enters
  the model context.
- the ``knowledge_base_query`` ToolSpec + the shared student RBAC matrix — the
  retrieval tool is ``read_only``, carries no org/audience-targeting parameter
  (a student literally cannot ask for another org's internal docs), and is
  invisible to a guest.

Case ``input`` keys:
- ``answer`` + ``sources`` → citation grounding.
- ``chunk`` → chunk injection neutralization.
- ``principal`` (+ ``tool_name``) → retrieval-tool RBAC visibility.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.evaluation.models import Probe
from app.ai.evaluation.runners import student_chat as sc
from app.ai.retrieval.citation_verify import verify_citations
from app.ai.safety.input_guard import neutralize_untrusted_text

_MARKER = "[removed]"


def _run_citation_seam(inp: dict[str, Any], data: dict[str, Any]) -> None:
    if "answer" not in inp:
        return
    result = verify_citations(str(inp["answer"]), list(inp.get("sources") or []))
    data["clean_answer"] = result.clean_answer
    data["hallucination_risk"] = result.hallucination_risk
    data["cited_count"] = result.cited_count
    data["grounded_count"] = result.grounded_count
    data["ungrounded_count"] = result.ungrounded_count


def _run_chunk_seam(inp: dict[str, Any], data: dict[str, Any]) -> None:
    chunk = inp.get("chunk")
    if chunk is None:
        return
    cleaned, neutralized = neutralize_untrusted_text(str(chunk))
    data["chunk_neutralized"] = bool(neutralized)
    data["chunk_cleaned"] = cleaned
    data["chunk_marker_present"] = _MARKER in (cleaned or "")


def _run_rbac_seam(inp: dict[str, Any], data: dict[str, Any]) -> None:
    name = inp.get("principal")
    if not name:
        return
    visible = sc.visible_tool_names(name)
    data["visible_count"] = len(visible)
    data["visible_tools"] = sorted(visible)
    tool_name = inp.get("tool_name")
    if tool_name:
        data["tool_visible"] = tool_name in visible
        spec = sc.TOOL_SPECS.get(tool_name)
        if spec is not None:
            data["authorized"] = sc.authorize_tool(sc.make_principal(name), spec)
            data["permission_class"] = spec.permission_class
            props = (spec.parameters or {}).get("properties") or {}
            data["schema_keys"] = sorted(props.keys())


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    data: dict[str, Any] = {}
    try:
        _run_citation_seam(inp, data)
        _run_chunk_seam(inp, data)
        _run_rbac_seam(inp, data)
    except Exception as exc:
        data["runner_error"] = type(exc).__name__
    blob = json.dumps(data, ensure_ascii=False, default=str).lower()
    return Probe(kind="student_rag", blob=blob, data=data)


def check(key: str, exp: Any, probe: Probe) -> str | None:  # noqa: C901
    d = probe.data
    if d.get("runner_error"):
        return f"runner crashed: {d['runner_error']}"

    # --- citation grounding ---
    if key == "hallucination_risk":
        got: Any = bool(d.get("hallucination_risk"))
        return None if got == bool(exp) else f"hallucination_risk expected {exp}, got {got}"
    if key == "cited_count":
        got = d.get("cited_count")
        return None if got == exp else f"cited_count expected {exp!r}, got {got!r}"
    if key == "grounded_count":
        got = d.get("grounded_count")
        return None if got == exp else f"grounded_count expected {exp!r}, got {got!r}"
    if key == "ungrounded_count":
        got = d.get("ungrounded_count")
        return None if got == exp else f"ungrounded_count expected {exp!r}, got {got!r}"
    if key == "clean_answer_contains":
        text = (d.get("clean_answer") or "").lower()
        terms = exp if isinstance(exp, list) else [exp]
        missing = [t for t in terms if str(t).lower() not in text]
        return None if not missing else f"clean_answer missing {missing}"
    if key == "clean_answer_excludes":
        text = (d.get("clean_answer") or "").lower()
        terms = exp if isinstance(exp, list) else [exp]
        present = [t for t in terms if str(t).lower() in text]
        return None if not present else f"clean_answer should exclude {present}"

    # --- chunk injection neutralization ---
    if key == "chunk_neutralized":
        got = bool(d.get("chunk_neutralized"))
        return None if got == bool(exp) else f"chunk_neutralized expected {exp}, got {got}"
    if key == "chunk_marker_present":
        got = bool(d.get("chunk_marker_present"))
        return None if got == bool(exp) else f"chunk_marker_present expected {exp}, got {got}"
    if key == "chunk_defuses":
        text = (d.get("chunk_cleaned") or "").lower()
        terms = exp if isinstance(exp, list) else [exp]
        present = [t for t in terms if str(t).lower() in text]
        return None if not present else f"injection phrase survived in chunk: {present}"
    if key == "chunk_preserves":
        text = (d.get("chunk_cleaned") or "").lower()
        terms = exp if isinstance(exp, list) else [exp]
        missing = [t for t in terms if str(t).lower() not in text]
        return None if not missing else f"chunk neutralization dropped benign data: {missing}"

    # --- retrieval-tool RBAC / audience isolation ---
    if key == "tool_visible":
        got = bool(d.get("tool_visible"))
        return None if got == bool(exp) else f"tool_visible expected {exp}, got {got}"
    if key == "authorized":
        got = bool(d.get("authorized"))
        return None if got == bool(exp) else f"authorized expected {exp}, got {got}"
    if key == "visible_count":
        got = d.get("visible_count")
        return None if got == exp else f"visible_count expected {exp}, got {got}"
    if key == "permission_class":
        got = d.get("permission_class")
        return None if got == exp else f"permission_class expected {exp!r}, got {got!r}"
    if key == "schema_excludes":
        keys = d.get("schema_keys") or []
        terms = exp if isinstance(exp, list) else [exp]
        leaked = [t for t in terms if t in keys]
        return None if not leaked else f"retrieval tool should not expose {leaked} (got {keys})"
    if key == "no_crash":
        return None
    return None  # unknown / informational key

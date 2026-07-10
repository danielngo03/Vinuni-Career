"""Golden multi-turn benchmark runner for the partner recruiter chatbot.

Where ``partner_chat`` evaluates the chatbot's safety/RBAC/routing seams one
*probe* at a time, ``partner_golden`` evaluates whole, hand-authored partner
CONVERSATIONS (a curated, higher-bar benchmark). Each dataset case is one
bilingual (vi/en) recruiter journey — a SEQUENCE of user turns — with
deterministic per-turn ``checks`` that run against the REAL seams under the
offline provider (no DB, no network, no real LLM):

- ``policy_orchestrator.check_policy`` — input guard + intent + refusal.
- ``model_router.route_turn`` / ``select_specs`` — tier + fail-open tool subset.
- ``native_loop.available_specs`` / ``authorize_tool`` — persona + RBAC matrix.
- ``tools.dispatch._validate_tool_args`` — §7 JSON-schema argument gate.
- ``gateway.output_guard.scrub_text`` — provider/model/token/key scrubbing.
- ``session_history._summarize_history`` — the rolling-memory summary seam
  (deterministic truncation offline) for cross-turn recall checks.

Reuse over reinvention: every per-turn state is produced by delegating the
turn's ``input`` to :func:`app.ai.evaluation.runners.partner_chat.run_case`,
and every per-turn ``check`` key that ``partner_chat`` already understands is
delegated to :func:`partner_chat.check`. Golden adds three conversation-native
check kinds on top:

- ``artifact_kind`` — the user-facing artifact a tool produces
  (chart/download/job_draft/image/candidate_list/event_list/...); maps the
  turn's ``tool_name`` through :data:`ARTIFACT_KIND`.
- ``phase`` — the leak-safe streaming status phase the turn would emit
  (understanding/retrieving/analyzing/drafting/visualizing/exporting/
  generating_image/composing); maps through :data:`PHASE_BY_ARTIFACT`. A live
  backend phase helper is imported DEFENSIVELY — its absence is surfaced as a
  pending integration item, never a crash.
- ``memory_recall`` — summarizes the accumulated user turns via the real memory
  seam and asserts an anchor established earlier in the conversation survives
  (and that the summary leaks nothing).

Case schema (documented in ``EVAL_NOTES.md``)::

    {"id": "pg_hp_...", "lang": "vi", "journey": "pipeline_funnel_chart",
     "turns": [
        {"input": {<partner_chat single-turn input>},
         "checks": [{"key": "route_tier", "expect": "default"}, ...]},
        ...],
     "expect": {"golden_pass": true, "no_provider_leak": true,
                "no_model_leak": true}}

The conversation-level ``expect`` block is what the offline harness enforces:
``golden_pass`` folds every per-turn check into a single pass/fail, and the
leakage keys scan the accumulated user-facing blob. Provider names, model ids,
aliases, token counts, latency, and prompt text NEVER enter the blob.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.evaluation.models import Probe
from app.ai.evaluation.runners import partner_chat as pc

# --------------------------------------------------------------------------- #
# Golden-native taxonomies (deterministic, leak-safe, file-referenced)         #
# --------------------------------------------------------------------------- #

# The user-facing artifact a tool produces. Keyed on the real TOOL_SPECS names.
# Lane B tools are included so cases stay strict the moment they register.
ARTIFACT_KIND: dict[str, str] = {
    "get_recruitment_analytics_chart": "chart",
    "get_hiring_funnel_diagram": "chart",
    "recruiting_analytics": "analytics",
    "get_partner_pipeline_summary": "summary",
    "pipeline_summary": "summary",
    "job_stats": "summary",
    "export_applications": "download",
    "export_jobs": "download",
    "export_interviews": "download",
    "export_offers": "download",
    "export_events": "download",
    "draft_job_description": "job_draft",
    "draft_job_from_text": "job_draft",
    "draft_job_from_attachment": "job_draft",
    "rewrite_job_description": "job_draft",
    "validate_job_draft": "job_draft",
    "create_job": "job_created",
    "generate_image": "image",
    "search_candidates": "candidate_list",
    "search_partner_candidates": "candidate_list",
    "get_candidate_detail": "candidate_profile",
    "get_upcoming_partner_events": "event_list",
    "get_upcoming_events": "event_list",
    "search_events": "event_list",
    "move_candidate_stage": "stage_change",
    "suggest_scorecard": "scorecard",
    "generate_screening_brief": "brief",
    "check_jd_bias": "bias_report",
    "get_partner_jobs": "job_list",
    "get_job_detail": "job_detail",
    "knowledge_base_query": "knowledge_answer",
}

# The leak-safe streaming status phase each artifact class maps to. This mirrors
# the backend's status vocabulary (understanding|retrieving|analyzing|drafting|
# visualizing|exporting|generating_image|composing) so a golden case can pin the
# phase the turn SHOULD surface without exposing any provider/model internal.
PHASE_BY_ARTIFACT: dict[str, str] = {
    "chart": "visualizing",
    "analytics": "analyzing",
    "summary": "retrieving",
    "download": "exporting",
    "job_draft": "drafting",
    "job_created": "drafting",
    "image": "generating_image",
    "candidate_list": "retrieving",
    "candidate_profile": "retrieving",
    "event_list": "retrieving",
    "stage_change": "composing",
    "scorecard": "analyzing",
    "brief": "analyzing",
    "bias_report": "analyzing",
    "job_list": "retrieving",
    "job_detail": "retrieving",
    "knowledge_answer": "retrieving",
}

# Golden check keys resolved locally (everything else delegates to partner_chat).
_GOLDEN_LOCAL_KEYS = frozenset({"artifact_kind", "phase", "memory_recall"})


def live_phase_helper() -> Any | None:
    """Return the backend's leak-safe phase helper if a lane has landed one.

    Imported defensively across a couple of plausible seams: the backend
    streaming lane may expose ``phase_for_intent`` / ``status_phase`` for the
    SSE ``status`` events. Absence is expected today (surfaced as a pending
    integration item by the benchmark) and must never crash the harness.
    """
    candidates = (
        ("app.modules.ai_assistant.application.chat_service", "phase_for_intent"),
        ("app.modules.ai_assistant.application.chat_service", "status_phase"),
        ("app.modules.ai_assistant.application.native_loop", "phase_for_intent"),
        ("app.modules.ai_assistant.application.response_formatter", "status_phase"),
    )
    for module_path, attr in candidates:
        try:
            module = __import__(module_path, fromlist=[attr])
        except ImportError:
            continue
        helper = getattr(module, attr, None)
        if callable(helper):
            return helper
    return None


# --------------------------------------------------------------------------- #
# Runner                                                                       #
# --------------------------------------------------------------------------- #


def _artifact_for(inp: dict[str, Any]) -> str | None:
    name = inp.get("tool_name")
    if not name:
        return None
    return ARTIFACT_KIND.get(str(name))


async def _summarize_transcript(transcript: list[Any]) -> str:
    """Run the accumulated user turns through the real memory seam (offline)."""
    from app.modules.ai_assistant.application.session_history import _summarize_history

    return await _summarize_history(transcript)


async def _eval_check(
    key: str,
    exp: Any,
    turn_probe: Probe,
    inp: dict[str, Any],
    transcript: list[Any],
) -> str | None:
    if key == "artifact_kind":
        got = _artifact_for(inp)
        if got is None and inp.get("pending_ok"):
            return None  # Lane B tool not registered yet — pending pass
        return None if got == exp else f"artifact_kind expected {exp!r}, got {got!r}"
    if key == "phase":
        artifact = _artifact_for(inp)
        got = PHASE_BY_ARTIFACT.get(artifact or "")
        if got is None and inp.get("pending_ok"):
            return None
        return None if got == exp else f"phase expected {exp!r}, got {got!r}"
    if key == "memory_recall":
        summary = await _summarize_transcript(transcript)
        anchors = exp if isinstance(exp, list) else [exp]
        missing = [a for a in anchors if str(a).lower() not in summary.lower()]
        if missing:
            return f"memory summary lost anchor(s) {missing}"
        # The rolling summary must itself be leak-free.
        leak = pc.scrub_text(summary)
        for term in ("gpt", "gemini", "openrouter", "prompt_tokens", "model_alias"):
            if term in leak.lower():
                return f"memory summary leaked {term!r}"
        return None
    # Everything else is a partner_chat-understood seam key.
    return pc.check(key, exp, turn_probe)


async def run_case(case: dict[str, Any]) -> Probe:
    from app.ai.gateway.base import AIMessage

    turns: list[dict[str, Any]] = case.get("turns") or []
    failed: list[str] = []
    pending: list[str] = []
    blob_parts: list[str] = []
    transcript: list[Any] = []

    phase_helper_present = live_phase_helper() is not None
    if not phase_helper_present:
        pending.append("live_phase_helper")

    for ti, turn in enumerate(turns):
        inp = turn.get("input") or {}
        try:
            turn_probe = await pc.run_case({"input": inp})
        except Exception as exc:  # a turn crash is itself a golden failure
            failed.append(f"t{ti}: runner crashed ({type(exc).__name__})")
            continue
        blob_parts.append(turn_probe.blob)

        # Grow the conversation transcript for cross-turn memory checks.
        utterance = inp.get("message") or inp.get("route_message")
        if utterance:
            transcript.append(AIMessage(role="user", content=str(utterance)))

        for chk in turn.get("checks") or []:
            key = str(chk.get("key"))
            exp = chk.get("expect")
            try:
                err = await _eval_check(key, exp, turn_probe, inp, transcript)
            except Exception as exc:
                err = f"check raised {type(exc).__name__}"
            if err:
                failed.append(f"t{ti}.{key}: {err}")

    data: dict[str, Any] = {
        "golden_pass": not failed,
        "failed_checks": failed,
        "journey": case.get("journey"),
        "lang": case.get("lang"),
        "turn_count": len(turns),
    }
    if pending:
        data["pending"] = sorted(set(pending))
    # The conversation blob is the union of every turn's already-scrubbed,
    # alias-free probe blob — the harness leak-scans it for provider/model/PII.
    blob = json.dumps(
        {"golden": data, "turns": blob_parts}, ensure_ascii=False, default=str
    ).lower()
    return Probe(kind="partner_golden", blob=blob, data=data)


# --------------------------------------------------------------------------- #
# Checker (conversation-level)                                                 #
# --------------------------------------------------------------------------- #


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Conversation-level assertions for ``partner_golden`` probes."""
    d = probe.data
    if key == "golden_pass":
        if d.get("golden_pass") == bool(exp):
            return None
        return f"golden checks failed: {d.get('failed_checks')}"
    if key == "journey":
        got = d.get("journey")
        return None if got == exp else f"journey expected {exp!r}, got {got!r}"
    if key == "turn_count_at_least":
        got = int(d.get("turn_count") or 0)
        return None if got >= int(exp) else f"turn_count {got} < expected {exp}"
    return None  # unknown / informational key

"""Golden multi-turn benchmark runner for the STUDENT career chatbot.

The student mirror of ``partner_golden``. Where ``student_chat`` evaluates the
chatbot's safety/RBAC/routing seams one *probe* at a time, ``student_golden``
evaluates whole, hand-authored student CONVERSATIONS (a curated, higher-bar
benchmark). Each dataset case is one bilingual (vi/en) student journey — a
SEQUENCE of user turns — with deterministic per-turn ``checks`` that run against
the REAL seams under the offline provider (no DB, no network, no real LLM):

- ``policy_orchestrator.check_policy`` — input guard + intent + refusal.
- ``model_router.route_turn`` / ``select_specs`` — tier + fail-open tool subset.
- ``native_loop.available_specs`` / ``authorize_tool`` — persona + RBAC matrix.
- ``tools.dispatch._validate_tool_args`` — §7 JSON-schema argument gate.
- ``gateway.output_guard.scrub_text`` — provider/model/token/key scrubbing.
- ``session_history._summarize_history`` — the rolling-memory summary seam
  (deterministic truncation offline) for cross-turn recall checks.

Every per-turn state is produced by delegating the turn's ``input`` to
:func:`app.ai.evaluation.runners.student_chat.run_case`, and every per-turn
``check`` key that ``student_chat`` already understands delegates to
:func:`student_chat.check`. Golden adds conversation-native check kinds:

- ``artifact_kind`` — the render artifact a tool produces (job_match_list /
  fit_breakdown / job_compare / cv_card / cv_compare); maps the turn's
  ``tool_name`` through :data:`ARTIFACT_KIND`. Frozen §3 render contract.
- ``render_kind`` — pins a FROZEN §3 render kind directly (used for
  ``cv_picker`` and ``career_brief`` which are branch/agent outputs of a tool
  rather than a distinct tool). Verifies the kind is real and maps to a
  leak-safe phase.
- ``phase`` — the leak-safe streaming status phase the turn would emit; maps
  through :data:`PHASE_BY_ARTIFACT`. A live backend phase helper is imported
  DEFENSIVELY — its absence is surfaced as a pending integration item, never a
  crash.
- ``memory_recall`` — summarizes the accumulated user turns via the real memory
  seam and asserts an anchor established earlier in the conversation survives.
- ``cv_marker_resolves`` — the CV-picker TWO-TURN resolution: after the student
  clicks a CV chip the FE sends a normal user turn carrying a machine-readable
  ``[[cv:{cv_id}]]`` marker; this check asserts the FROZEN marker parses to the
  chosen cv_id and is stripped from the displayed text. Lane A's live selection
  pre-processor is probed DEFENSIVELY (absence → pending item, never a crash).

The conversation-level ``expect`` block is what the offline harness enforces:
``golden_pass`` folds every per-turn check into a single pass/fail, and the
leakage keys scan the accumulated user-facing blob. Provider names, model ids,
aliases, token counts, latency, and prompt text NEVER enter the blob.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai.evaluation.models import Probe
from app.ai.evaluation.runners import student_chat as sc

# --------------------------------------------------------------------------- #
# Golden-native taxonomies (deterministic, leak-safe, frozen §3 contract)      #
# --------------------------------------------------------------------------- #

# The render artifact a tool produces. Keyed on the FROZEN new student tool
# names (Lane B) so cases stay valid the moment the tools register.
ARTIFACT_KIND: dict[str, str] = {
    "match_cv_to_jobs": "job_match_list",
    "explain_job_fit": "fit_breakdown",
    "compare_jobs": "job_compare",
    "show_cv": "cv_card",
    "compare_cvs": "cv_compare",
}

# The FROZEN §3 student render kinds. cv_picker + career_brief are branch/agent
# outputs (not a distinct tool) so a golden turn pins them via ``render_kind``.
STUDENT_RENDER_KINDS: frozenset[str] = frozenset(
    {
        "cv_card",
        "job_match_list",
        "job_compare",
        "fit_breakdown",
        "cv_compare",
        "cv_picker",
        "career_brief",
    }
)

# The leak-safe streaming status phase each render class maps to. Mirrors the
# backend's status vocabulary (understanding|retrieving|analyzing|drafting|
# visualizing|exporting|generating_image|composing) so a golden case can pin the
# phase the turn SHOULD surface without exposing any provider/model internal.
PHASE_BY_ARTIFACT: dict[str, str] = {
    "job_match_list": "analyzing",
    "fit_breakdown": "analyzing",
    "job_compare": "analyzing",
    "cv_compare": "analyzing",
    "career_brief": "analyzing",
    "cv_card": "retrieving",
    "cv_picker": "composing",
}

# Golden check keys resolved locally (everything else delegates to student_chat).
_GOLDEN_LOCAL_KEYS = frozenset(
    {"artifact_kind", "render_kind", "phase", "memory_recall", "cv_marker_resolves"}
)

# FROZEN CV-selection marker (§3): a normal user turn re-issued from a picker
# click carries ``[[cv:{cv_id}]]`` appended (stripped before display).
_CV_MARKER_RE = re.compile(r"\[\[cv:([^\]]+)\]\]")


def live_phase_helper() -> Any | None:
    """Return the backend's leak-safe phase helper if a lane has landed one.

    Imported defensively across a couple of plausible seams; absence is expected
    today (surfaced as a pending integration item by the benchmark) and must
    never crash the harness.
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


def live_cv_selection_helper() -> Any | None:
    """Return Lane A's ``[[cv:...]]`` selection pre-processor if it has landed.

    Lane A adds a tiny pre-processor: when a ``[[cv:...]]`` marker is present it
    injects a system hint so the model re-calls the pending CV tool with that
    cv_id. Probed defensively — its absence today is a pending integration item,
    never a crash; the FROZEN marker CONTRACT is still tested deterministically.
    """
    candidates = (
        ("app.modules.ai_assistant.application.chat_service", "extract_cv_selection"),
        ("app.modules.ai_assistant.application.chat_service", "resolve_cv_marker"),
        ("app.modules.ai_assistant.application.native_loop", "extract_cv_selection"),
        ("app.modules.ai_assistant.application.response_formatter", "extract_cv_selection"),
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
    if key == "render_kind":
        if exp not in STUDENT_RENDER_KINDS:
            return f"render_kind {exp!r} is not a frozen §3 student render kind"
        if exp not in PHASE_BY_ARTIFACT:
            return f"render_kind {exp!r} has no leak-safe phase mapping"
        got = inp.get("render_kind")
        return None if got == exp else f"render_kind expected {exp!r}, got {got!r}"
    if key == "phase":
        artifact = _artifact_for(inp) or inp.get("render_kind")
        got = PHASE_BY_ARTIFACT.get(artifact or "")
        if got is None and inp.get("pending_ok"):
            return None
        return None if got == exp else f"phase expected {exp!r}, got {got!r}"
    if key == "cv_marker_resolves":
        utter = inp.get("message") or inp.get("route_message") or ""
        m = _CV_MARKER_RE.search(str(utter))
        got = m.group(1) if m else None
        if got != exp:
            return f"cv selection marker expected {exp!r}, got {got!r}"
        display = _CV_MARKER_RE.sub("", str(utter))
        if "[[cv" in display:
            return "cv selection marker not stripped from displayed text"
        return None
    if key == "memory_recall":
        summary = await _summarize_transcript(transcript)
        anchors = exp if isinstance(exp, list) else [exp]
        missing = [a for a in anchors if str(a).lower() not in summary.lower()]
        if missing:
            return f"memory summary lost anchor(s) {missing}"
        # The rolling summary must itself be leak-free.
        leak = sc.scrub_text(summary)
        for term in ("gpt", "gemini", "openrouter", "prompt_tokens", "model_alias"):
            if term in leak.lower():
                return f"memory summary leaked {term!r}"
        return None
    # Everything else is a student_chat-understood seam key.
    return sc.check(key, exp, turn_probe)


async def run_case(case: dict[str, Any]) -> Probe:
    from app.ai.gateway.base import AIMessage

    turns: list[dict[str, Any]] = case.get("turns") or []
    failed: list[str] = []
    pending: list[str] = []
    blob_parts: list[str] = []
    transcript: list[Any] = []

    if live_phase_helper() is None:
        pending.append("live_phase_helper")
    if live_cv_selection_helper() is None:
        pending.append("live_cv_selection_helper")

    for ti, turn in enumerate(turns):
        inp = turn.get("input") or {}
        try:
            turn_probe = await sc.run_case({"input": inp})
        except Exception as exc:  # a turn crash is itself a golden failure
            failed.append(f"t{ti}: runner crashed ({type(exc).__name__})")
            continue
        blob_parts.append(turn_probe.blob)

        # Grow the conversation transcript for cross-turn memory checks (marker
        # stripped so a memory anchor never carries the machine-readable tag).
        utterance = inp.get("message") or inp.get("route_message")
        if utterance:
            display = _CV_MARKER_RE.sub("", str(utterance)).strip()
            transcript.append(AIMessage(role="user", content=display))

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
    return Probe(kind="student_golden", blob=blob, data=data)


# --------------------------------------------------------------------------- #
# Checker (conversation-level)                                                 #
# --------------------------------------------------------------------------- #


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Conversation-level assertions for ``student_golden`` probes."""
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

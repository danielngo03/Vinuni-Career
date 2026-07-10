"""Eval runner + checker for the ``partner_jd_builder`` family.

Scenarios of partial / complete / adversarial job-draft payloads flowing
through the JD-builder validation seams (all pure — no DB, no LLM call):

- **Draft validation core** —
  ``app.modules.ai_assistant.application.tools.jd_builder``:
  ``coerce_draft_input`` (lift + type-coerce the recruiter/model-supplied
  fields, keeping invalid enum values so they surface as warnings) followed by
  ``evaluate_draft`` → ``(missing_required, warnings, ready)``. This is the
  exact deterministic pipeline behind the ``validate_job_draft`` assistant
  tool (frozen ``job_draft`` artifact contract). Required fields:
  ``title``, ``description``, ``employment_type``.
- **Bias screening** — ``app.ai.safety.bias_detection.check_bias`` over the
  draft's text fields, the same engine ``evaluate_draft`` consults for its
  ``bias_language`` warning. Asserted independently so a regression in either
  layer is caught.

The core import is kept lazy + guarded: parallel lanes edit the tools package
while this eval exists, and a transient import error must fail THIS family's
cases with a clear message instead of crashing the whole harness import chain.

Privacy contract: the validator's OUTPUT must never echo the raw draft text
back — the probe blob contains only field names, missing/ready results,
warning codes, and bias findings, so injected instructions, PII, keys, or
model-name bait pasted into a draft can never leak through this family's
user-facing payload.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.evaluation.models import Probe
from app.ai.safety.bias_detection import check_bias
from app.modules.ai_assistant.application.response_formatter import ai_unavailable_reply

_TEXT_FIELDS = ("title", "description", "requirements", "benefits")


def core_probe(draft: dict[str, Any]) -> dict[str, Any]:
    """Run the pure validate-job-draft core: coerce + evaluate.

    Returns ``{"available": bool, "error": str|None, "missing_required": [...],
    "warning_codes": [...], "ready": bool}``.
    """
    try:
        from app.modules.ai_assistant.application.tools import jd_builder
    except ImportError:
        return {
            "available": False,
            "error": (
                "jd_builder not importable — the validate_job_draft core "
                "(coerce_draft_input + evaluate_draft) landed 2026-07-11; "
                "its absence is a regression"
            ),
        }
    try:
        coerced = jd_builder.coerce_draft_input(dict(draft))
        missing_required, warnings, ready = jd_builder.evaluate_draft(coerced)
    except Exception as exc:
        return {"available": True, "error": f"core raised {type(exc).__name__}"}
    return {
        "available": True,
        "error": None,
        "missing_required": sorted(str(f).lower() for f in missing_required),
        "warning_codes": sorted(str(w.get("code")) for w in warnings),
        "ready": bool(ready),
    }


def _run_bias_seam(draft: dict[str, Any], data: dict[str, Any]) -> None:
    text = " \n".join(str(draft.get(f) or "") for f in _TEXT_FIELDS)
    result = check_bias(text[:6000])
    data["bias_flagged"] = result.flagged
    data["bias_high_risk"] = result.requires_human_review
    data["bias_categories"] = sorted({f.category for f in result.findings})
    # matched_phrase comes only from the bias rule regexes (never PII/keys).
    data["bias_findings"] = [
        {"category": f.category, "risk_level": f.risk_level, "matched_phrase": f.matched_phrase}
        for f in result.findings
    ]


def _run_core_seam(draft: dict[str, Any], data: dict[str, Any]) -> None:
    probe = core_probe(draft)
    data["core_available"] = probe["available"]
    if probe.get("error"):
        data["core_error"] = probe["error"]
        return
    data["missing_required"] = probe["missing_required"]
    data["warning_codes"] = probe["warning_codes"]
    data["ready"] = probe["ready"]


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    data: dict[str, Any] = {}
    try:
        if inp.get("check") == "ai_unavailable_reply":
            data["reply_text"] = ai_unavailable_reply(str(inp.get("locale") or "vi"))
        if "draft" in inp:
            draft = inp.get("draft") or {}
            if not isinstance(draft, dict):
                draft = {}
            # NOTE: raw draft values are intentionally NOT copied into ``data``
            # — only field names + validation/bias outcomes (privacy contract).
            data["draft_fields"] = sorted(str(k) for k in draft)
            _run_bias_seam(draft, data)
            _run_core_seam(draft, data)
    except Exception as exc:
        data["runner_error"] = type(exc).__name__
    blob = json.dumps(data, ensure_ascii=False, default=str).lower()
    return Probe(kind="partner_jd_builder", blob=blob, data=data)


_CORE_KEYS = frozenset(
    {
        "missing_required_includes",
        "missing_required_excludes",
        "ready",
        "warning_codes_contains",
        "warning_codes_excludes",
    }
)


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``partner_jd_builder`` probes."""
    d = probe.data
    if d.get("runner_error"):
        return f"runner crashed: {d['runner_error']}"
    if key in _CORE_KEYS and d.get("core_error"):
        return f"validation core unavailable: {d['core_error']}"

    if key == "missing_required_includes":
        missing = d.get("missing_required") or []
        wanted = exp if isinstance(exp, list) else [exp]
        absent = [w for w in wanted if str(w).lower() not in missing]
        return None if not absent else f"missing_required should include {absent} (got {missing})"
    if key == "missing_required_excludes":
        missing = d.get("missing_required") or []
        unwanted = exp if isinstance(exp, list) else [exp]
        present = [u for u in unwanted if str(u).lower() in missing]
        return None if not present else f"missing_required should exclude {present}"
    if key == "ready":
        got = d.get("ready")
        if got is None:
            return "validation core reported no ready flag"
        return None if got == bool(exp) else f"ready expected {exp}, got {got}"
    if key == "warning_codes_contains":
        codes = d.get("warning_codes") or []
        wanted = exp if isinstance(exp, list) else [exp]
        absent = [w for w in wanted if w not in codes]
        return None if not absent else f"warning codes should include {absent} (got {codes})"
    if key == "warning_codes_excludes":
        codes = d.get("warning_codes") or []
        unwanted = exp if isinstance(exp, list) else [exp]
        present = [u for u in unwanted if u in codes]
        return None if not present else f"warning codes should exclude {present}"

    if key == "bias_flagged":
        got = bool(d.get("bias_flagged"))
        return None if got == bool(exp) else f"bias_flagged expected {exp}, got {got}"
    if key == "bias_high_risk":
        got = bool(d.get("bias_high_risk"))
        return None if got == bool(exp) else f"bias_high_risk expected {exp}, got {got}"
    if key == "bias_category_contains":
        cats = d.get("bias_categories") or []
        return None if exp in cats else f"expected bias category {exp!r} in {cats}"

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

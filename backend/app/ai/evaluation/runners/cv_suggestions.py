"""Eval runner + checker for the ``cv_ai_suggestions`` family.

Covers 7 CV task types (``draft_cv_from_profile``, ``fill_cv_template_from_sources``,
``generate_cv_bullets``, ``rewrite_cv_section``, ``optimize_cv_for_job``,
``ats_keyword_suggestions``, ``cv_fabrication_check``) via the real
``app.ai.cv.tasks.run_cv_task`` dispatcher under the deterministic offline
provider.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.cv.tasks import CvAiContext, CvAiResult, run_cv_task
from app.ai.evaluation.leak_checks import no_forbidden_terms
from app.ai.evaluation.models import Probe
from app.ai.evaluation.runners._offline_provider import maybe_provider_down
from app.shared.exceptions import AIUnavailableError


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    ctx = CvAiContext(
        task_type=case["task_type"],
        language=inp.get("language", "vi"),
        instruction=inp.get("instruction"),
        raw_notes=inp.get("raw_notes"),
        cv_sections=inp.get("cv_sections") or [],
        target_section=inp.get("target_section"),
        profile_sections=inp.get("profile_sections"),
        upload_extracted=inp.get("upload_extracted"),
        source_cv_sections=inp.get("source_cv_sections"),
        job=inp.get("job"),
    )
    provider_down = inp.get("provider") == "unavailable"
    try:
        with maybe_provider_down(provider_down):
            result: CvAiResult = await run_cv_task(ctx)
    except AIUnavailableError as exc:
        return Probe(kind="cv", raised_code=exc.code, raised_message=str(exc))

    diff = result.to_diff()
    payload = {"status": "pending", "diff": diff}
    return Probe(
        kind="cv",
        blob=json.dumps(payload, ensure_ascii=False).lower(),
        diff=diff,
        after_blob=json.dumps(diff.get("after"), ensure_ascii=False).lower(),
        summary=result.summary,
    )


def _after_items(probe: Probe) -> list[Any]:
    diff = probe.diff or {}
    sections = (diff.get("after") or {}).get("sections") or []
    if not sections:
        return []
    content = sections[0].get("content") or {}
    items = content.get("items")
    return items if isinstance(items, list) else []


def _missing_terms(probe: Probe) -> list[str]:
    diff = probe.diff or {}
    if isinstance(diff.get("keywords"), list):
        return [str(k) for k in diff["keywords"]]
    sugg = diff.get("suggestions") or {}
    missing = sugg.get("missing")
    return [str(k) for k in missing] if isinstance(missing, list) else []


def check(key: str, exp: Any, probe: Probe) -> str | None:  # noqa: C901
    if key == "error_code":
        return None if probe.raised_code == exp else (
            f"expected error_code {exp!r}, got {probe.raised_code!r}"
        )
    if key == "no_stack_trace":
        bad = "traceback" in probe.raised_message.lower()
        return "stack trace leaked in error message" if bad else None
    if key == "degrades_to_deterministic":
        return None if probe.raised_code is None and probe.diff is not None else (
            "expected deterministic success but the task degraded/raised"
        )
    if probe.diff is None:  # any remaining cv check needs a diff
        return f"no diff produced (task raised {probe.raised_code!r})"
    if key == "applicable":
        return None if bool(probe.diff.get("applicable")) == bool(exp) else (
            f"applicable expected {exp}, got {probe.diff.get('applicable')}"
        )
    if key == "requires_fact_confirmation":
        got = bool(probe.diff.get("requires_fact_confirmation"))
        return None if got == bool(exp) else (
            f"requires_fact_confirmation expected {exp}, got {got}"
        )
    if key in ("after_contains",):
        return None if str(exp).lower() in (probe.after_blob or "") else (
            f"after content should contain {exp!r}"
        )
    if key.startswith("after_not_contains"):
        return None if str(exp).lower() not in (probe.after_blob or "") else (
            f"after content should NOT contain {exp!r}"
        )
    if key == "after_bullet_count":
        n = len(_after_items(probe))
        return None if n == int(exp) else f"after bullet count expected {exp}, got {n}"
    if key == "filled":
        sections = (probe.diff.get("after") or {}).get("sections") or []
        return None if len(sections) == int(exp) else (
            f"filled sections expected {exp}, got {len(sections)}"
        )
    if key == "ordering_first":
        sections = (probe.diff.get("after") or {}).get("sections") or []
        first = sections[0].get("section_type") if sections else None
        return None if first == exp else f"first section expected {exp!r}, got {first!r}"
    if key == "missing_contains":
        return None if str(exp) in _missing_terms(probe) else (
            f"missing keywords should contain {exp!r} (got {_missing_terms(probe)})"
        )
    if key == "missing_count":
        n = len(_missing_terms(probe))
        return None if n == int(exp) else f"missing count expected {exp}, got {n}"
    if key == "summary_mentions_insufficient":
        s = (probe.summary or "").lower()
        ok = ("insufficient" in s) or ("chưa đủ" in s) or ("not enough" in s)
        return None if ok else "summary should mention insufficient data"
    if key in ("no_crash",):
        return None  # reaching here means the task ran without an unexpected crash
    if key in (
        "grounded_in_owner_data_only",
        "no_evidence_from_other_users",
    ):
        return no_forbidden_terms(probe.blob)  # structural: owner-scoped + no leak
    if key == "loads_other_user_cv":
        # Expected false: no foreign CV content may appear in the grounded output.
        return None if "other_user_cv" not in probe.blob else (
            "foreign (other-user) CV content leaked into the diff"
        )
    return None  # unknown / informational key

"""Eval runner + checker for the ``interview_grounding`` family.

Deterministic, zero-LLM coverage of the PURE grounding composition that anchors a
mock interview (``app.modules.mock_interview.application.grounding_service``):

- ``_infer_focus``      — technical / mixed / behavioral inference from the JD;
- ``_infer_difficulty`` — foundational / intermediate / advanced from seniority +
  ``experience_min_years``;
- ``_job_requirements`` — concrete JD requirement bullets (string requirements,
  ``candidate_requirements`` dict, degree, experience), each ``sanitize_instruction``-
  cleaned so an injection embedded in a JD can never survive into the system prompt;
- the ``low_signal`` flag — a near-empty JD (no requirements, no required skills,
  tiny description) is flagged so the UI sets honest expectations;
- owner-scoped ``matched_skills`` / ``gaps`` — cleaned + capped from the SELECTED
  CV's read-model only (they can never carry another owner's data because the
  runner reads exactly the provided ``selected`` block).

The DB/RBAC/CV-picker path (``build_interview_grounding`` → ``job_fit_for_job``)
has its own service-layer integration tests; this family calls the pure helpers
directly (no DB, no principal, no LLM) so every expected output is exact.

Case input schema (``case["input"]``):
  - ``job``      : dict — the JD read-model shape (title, seniority_level,
                   required_skills, preferred_skills, requirements,
                   candidate_requirements, degree_required, experience_min/max_years,
                   description).
  - ``selected`` : dict — the selected CV block (matched_skills, gaps) — optional.
  - ``locale``   : str  — user locale (default "vi").

Expectation keys handled here:
  - ``focus_equals`` / ``difficulty_equals`` : str — exact inference result.
  - ``low_signal``                           : bool — the near-empty-JD flag.
  - ``requirements_count_at_least`` / ``_at_most`` : int — requirement-bullet count.
  - ``matched_count_at_most`` / ``gaps_count_at_most`` : int — cap enforcement.
  - ``blob_contains`` / ``blob_excludes``    : substring assertions on the grounding.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.evaluation.models import Probe
from app.modules.mock_interview.application import grounding_service as gs

_KIND = "interview_grounding"


def _low_signal(job: dict[str, Any]) -> bool:
    """Mirror ``build_grounding``'s near-empty-JD flag (pure fragment)."""

    return bool(
        not gs._job_requirements(job)
        and not gs._clean_list(job.get("required_skills"), limit=20)
        and len(gs._clean(job.get("description"))) < 120
    )


async def run_case(case: dict[str, Any]) -> Probe:
    """Compose the pure grounding from a JD + selected-CV block, no DB/LLM."""

    inp = case.get("input") or {}
    job = inp.get("job") or {}
    selected = inp.get("selected") or {}
    locale = inp.get("locale") or "vi"

    grounding = {
        "locale": locale,
        "focus": gs._infer_focus(job),
        "difficulty": gs._infer_difficulty(job),
        "job": {
            "title": gs._clean(job.get("title")),
            "requirements": gs._job_requirements(job),
            "required_skills": gs._clean_list(job.get("required_skills"), limit=20),
            "preferred_skills": gs._clean_list(job.get("preferred_skills"), limit=12),
            "seniority_level": job.get("seniority_level"),
            "experience": gs._experience_str(job),
        },
        "matched_skills": gs._clean_list(selected.get("matched_skills"), limit=15),
        "gaps": gs._clean_list(selected.get("gaps"), limit=15),
        "low_signal": _low_signal(job),
    }

    blob = json.dumps(grounding, ensure_ascii=False, default=str).lower()
    return Probe(kind=_KIND, blob=blob, data={"grounding": grounding})


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``interview_grounding`` probes."""

    grounding: dict[str, Any] = (probe.data or {}).get("grounding") or {}
    job = grounding.get("job") or {}

    if key == "focus_equals":
        got = grounding.get("focus")
        return None if got == exp else f"focus expected {exp!r}, got {got!r}"
    if key == "difficulty_equals":
        got = grounding.get("difficulty")
        return None if got == exp else f"difficulty expected {exp!r}, got {got!r}"
    if key == "low_signal":
        got = bool(grounding.get("low_signal"))
        return None if got == bool(exp) else f"low_signal expected {exp}, got {got}"
    if key == "requirements_count_at_least":
        n = len(job.get("requirements") or [])
        return None if n >= int(exp) else f"requirements count {n} below floor {exp}"
    if key == "requirements_count_at_most":
        n = len(job.get("requirements") or [])
        return None if n <= int(exp) else f"requirements count {n} exceeds cap {exp}"
    if key == "matched_count_at_most":
        n = len(grounding.get("matched_skills") or [])
        return None if n <= int(exp) else f"matched_skills count {n} exceeds cap {exp}"
    if key == "gaps_count_at_most":
        n = len(grounding.get("gaps") or [])
        return None if n <= int(exp) else f"gaps count {n} exceeds cap {exp}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"grounding should contain {exp!r}"
    if key == "blob_excludes":
        terms = exp if isinstance(exp, list) else [exp]
        for term in terms:
            if str(term).lower() in probe.blob:
                return f"grounding should exclude {term!r}"
        return None
    return None  # unknown / informational key

"""Logged-in student job intelligence (E35: B-535..B-540).

Composes the already-shipped CV-to-job fit scorer
(``documents.application.job_fit_service``, deterministic + optional AI
explanation) with a NEW student-aware, bucketed competition read model
(``opportunities.application.competition_service.student_competition_intelligence``)
plus deterministic, non-AI learning-gap and next-action guidance, per
``docs/API_CONTRACTS.md`` "Student Job Intelligence" and
``docs/PRODUCT_REALITY_REBUILD_SPEC.md`` Matching/Competition.

Cross-module direction note: this composition lives in ``opportunities``
(the endpoint is job-detail-centric, ``GET /jobs/{job_id}/student-intelligence``,
and apply-readiness/deadline concerns are Job/Application-owned concepts). It
imports the ``documents`` module's public ``job_fit_service.job_fit_for_job``
application-layer function the same way ``documents`` already imports
``opportunities.application.job_fit_read`` — both are public read-facade calls,
not reaches into another module's ORM/domain internals, so this does not
introduce an import cycle.

Guarantees:

- Authenticated-student only (persona check here; auth itself is enforced by
  the router's ``get_current_auth`` dependency).
- Never exposes other applicants, exact ranks, raw CV text, raw model
  confidence, provider/model names, prompts, token counts, or hiring
  guarantees — the competition sub-object is bucketed/aggregate only
  (``competition_service.student_competition_intelligence``).
- Guests never reach this function (the router requires auth; a non-student
  persona is rejected with ``PermissionDeniedError``).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.application import job_fit_service
from app.modules.opportunities.application import competition_service
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import Principal

# Fit score -> DATA_MODEL.md `cv_job_fit_reports.score_label` vocabulary.
_FIT_LABEL_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (85, "strong_fit"),
    (70, "good_fit"),
    (50, "possible_fit"),
    (0, "weak_fit"),
)

# Deterministic, generic learning-resource fallback by keyword family. Real
# curated-resource catalog integration is a later-phase read model; until then
# every gap gets a truthful, non-branded, actionable suggestion (never a fake
# specific course/provider name).
_GENERIC_RESOURCE_SUGGESTION = (
    "Build a small portfolio project that demonstrates {skill}, or add a line to "
    "your CV describing real experience with it if you already have some."
)


def _fit_label(score: int) -> str:
    for threshold, label in _FIT_LABEL_THRESHOLDS:
        if score >= threshold:
            return label
    return "weak_fit"


def _improvement_actions(result: dict | None) -> list[str]:
    if result is None:
        return ["Create your first CV to unlock a personalized fit score for this job."]

    actions: list[str] = []
    bands = result["bands"]
    if bands["skills"] < 70 and result["gaps"]:
        top_gaps = ", ".join(result["gaps"][:3])
        actions.append(f"Add evidence for: {top_gaps} (if you have real experience with them).")
    if bands["experience"] < 60:
        actions.append(
            "Add a work experience or project section showing hands-on evidence for this role."
        )
    if bands["quality"] < 60:
        if result["last_updated_days"] > 60:
            actions.append("Update your CV — it hasn't been edited in over two months.")
        else:
            actions.append("Fill in more core sections (summary, education, skills) for completeness.")
    if result["stale"] and "hasn't been edited" not in " ".join(actions):
        actions.append("This CV is stale — refresh it before applying.")
    return actions


def _present_fit(result: dict | None, *, signal: str) -> dict:
    if result is None:
        return {
            "status": "no_active_cv",
            "score": None,
            "label": None,
            "bands": None,
            "matched_evidence": [],
            "gaps": [],
            "improvement_actions": _improvement_actions(None),
        }
    return {
        "status": "scored",
        "score": result["score"],
        "label": _fit_label(result["score"]),
        "bands": result["bands"],
        "matched_evidence": result["matched_skills"],
        "gaps": result["gaps"],
        "improvement_actions": _improvement_actions(result),
        "signal": signal,
        "stale": result["stale"],
        "explanation": result.get("explanation"),
    }


def _learning_gaps(result: dict | None) -> list[dict]:
    if result is None or not result["gaps"]:
        return []
    return [
        {
            "skill": gap,
            "suggestion": _GENERIC_RESOURCE_SUGGESTION.format(skill=gap),
            "resource_type": "practice_project",
        }
        for gap in result["gaps"][:5]
    ]


def _next_actions(
    *,
    best_cv_id: str | None,
    selected_cv_id: str | None,
    has_active_cv: bool,
    fit_result: dict | None,
    apply_readiness: dict,
) -> list[dict]:
    actions: list[dict] = []
    if not has_active_cv:
        actions.append({
            "action": "improve_cv",
            "label": "Create a CV to see your fit for this job",
        })
    else:
        if best_cv_id and best_cv_id != selected_cv_id:
            actions.append({
                "action": "select_best_cv",
                "cv_id": best_cv_id,
                "label": "Use your best-matching CV for this job",
            })
        if fit_result and (fit_result["bands"]["skills"] < 70 or fit_result["stale"]):
            actions.append({
                "action": "improve_cv",
                "cv_id": selected_cv_id or best_cv_id,
                "label": "Improve your CV before applying",
            })

    actions.append({
        "action": "apply",
        "label": "Apply to this job",
        "ready": apply_readiness["ready"],
        "blocked_reason": apply_readiness["blocked_reason"],
    })
    actions.append({"action": "save_job", "label": "Save this job for later"})
    actions.append({
        "action": "compare_adjacent_roles",
        "label": "Compare with similar roles",
    })
    return actions


def _apply_readiness(
    *, has_active_cv: bool, already_applied: bool, deadline_passed: bool
) -> dict:
    blocked_reason: str | None = None
    if already_applied:
        blocked_reason = "already_applied"
    elif deadline_passed:
        blocked_reason = "deadline_passed"
    elif not has_active_cv:
        blocked_reason = "no_active_cv"

    return {
        "ready": blocked_reason is None,
        "blocked_reason": blocked_reason,
        "already_applied": already_applied,
        "deadline_passed": deadline_passed,
        "has_active_cv": has_active_cv,
    }


async def student_intelligence_for_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    cv_id: uuid.UUID | None,
) -> dict:
    """The combined, login-gated job-detail intelligence payload (B-535..B-540).

    Raises ``PermissionDeniedError`` for any non-student persona (the router
    already requires authentication via ``get_current_auth``) and
    ``ResourceNotFoundError`` (via the underlying services) for hidden/closed/
    missing jobs — the same non-enumerable 404 semantics as the sibling
    ``/cvs/job-fit`` and ``/jobs/{job_id}/competition-signal`` endpoints.
    """

    if principal.persona != "student":
        raise PermissionDeniedError()

    fit_payload = await job_fit_service.job_fit_for_job(
        session, principal=principal, job_id=job_id
    )
    results = fit_payload["results"]
    by_id = {r["cv_id"]: r for r in results}
    best_cv_id = fit_payload["recommended_cv_id"]

    selected_cv_id = str(cv_id) if cv_id and str(cv_id) in by_id else None
    active_result = by_id.get(selected_cv_id) if selected_cv_id else by_id.get(best_cv_id)

    fit = _present_fit(active_result, signal=fit_payload["signal"])

    competition = await competition_service.student_competition_intelligence(
        session,
        principal=principal,
        job_id=job_id,
        student_fit_score=active_result["score"] if active_result else None,
    )
    deadline_passed = bool(competition.pop("_deadline_passed"))
    already_applied = bool(competition.pop("_already_applied"))

    has_active_cv = bool(results)
    apply_readiness = _apply_readiness(
        has_active_cv=has_active_cv,
        already_applied=already_applied,
        deadline_passed=deadline_passed,
    )
    next_actions = _next_actions(
        best_cv_id=best_cv_id,
        selected_cv_id=selected_cv_id,
        has_active_cv=has_active_cv,
        fit_result=active_result,
        apply_readiness=apply_readiness,
    )

    return {
        "job_id": str(job_id),
        "selected_cv_id": selected_cv_id,
        "best_cv_id": best_cv_id,
        "fit": fit,
        "competition": competition,
        "learning_gaps": _learning_gaps(active_result),
        "apply_readiness": apply_readiness,
        "next_actions": next_actions,
    }

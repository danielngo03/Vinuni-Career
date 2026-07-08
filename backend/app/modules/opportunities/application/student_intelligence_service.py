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
from app.modules.opportunities.domain import learning_resources
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import Principal

# Fit score -> DATA_MODEL.md `cv_job_fit_reports.score_label` vocabulary.
_FIT_LABEL_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (85, "strong_fit"),
    (70, "good_fit"),
    (50, "possible_fit"),
    (0, "weak_fit"),
)

# --------------------------------------------------------------------------- #
# Localized guidance strings (vi-first product; frontend renders these raw).   #
# --------------------------------------------------------------------------- #
#
# The frontend renders ``improvement_actions``, ``learning_gaps[].suggestion``
# and competition ``guidance`` as raw backend strings (it only localizes
# ``next_actions`` by the action CODE), so every user-facing sentence here is
# localized server-side. ``{skill}``/``{top_gaps}`` interpolation is preserved.

_DEFAULT_LOCALE = "vi"

# Per-gap learning-resource copy now lives in the curated
# ``opportunities.domain.learning_resources`` catalog (specific resource_type +
# tailored suggestion per skill, generic fallback otherwise); the strings below
# cover the fit/next-action guidance only.
_STRINGS: dict[str, dict[str, str]] = {
    "vi": {
        "no_cv": (
            "Tạo CV đầu tiên của bạn để mở khóa điểm phù hợp cá nhân hóa cho công "
            "việc này."
        ),
        "add_evidence": (
            "Bổ sung bằng chứng cho: {top_gaps} (nếu bạn thực sự có kinh nghiệm với "
            "chúng)."
        ),
        "add_experience": (
            "Thêm phần kinh nghiệm làm việc hoặc dự án thể hiện bằng chứng thực tế "
            "cho vai trò này."
        ),
        "domain_mismatch": (
            "Công việc này thuộc lĩnh vực khác với CV của bạn — hãy làm nổi bật kinh "
            "nghiệm hoặc kỹ năng có thể chuyển đổi phù hợp với ngành này."
        ),
        "update_cv_stale": (
            "Cập nhật CV của bạn — CV chưa được chỉnh sửa trong hơn hai tháng."
        ),
        "fill_core_sections": (
            "Điền thêm các phần cốt lõi (tóm tắt, học vấn, kỹ năng) để hoàn thiện CV."
        ),
        "refresh_stale": (
            "CV này đã cũ — hãy làm mới trước khi ứng tuyển."
        ),
        "next_create_cv": "Tạo CV để xem mức độ phù hợp của bạn với công việc này",
        "next_select_best_cv": "Dùng CV phù hợp nhất cho công việc này",
        "next_improve_cv": "Cải thiện CV trước khi ứng tuyển",
        "next_apply": "Ứng tuyển công việc này",
        "next_save_job": "Lưu công việc này để xem sau",
        "next_compare": "So sánh với các vai trò tương tự",
    },
    "en": {
        "no_cv": (
            "Create your first CV to unlock a personalized fit score for this job."
        ),
        "add_evidence": (
            "Add evidence for: {top_gaps} (if you have real experience with them)."
        ),
        "add_experience": (
            "Add a work experience or project section showing hands-on evidence for "
            "this role."
        ),
        "domain_mismatch": (
            "This role is in a different field from your CV — highlight any "
            "transferable experience or skills relevant to this industry."
        ),
        "update_cv_stale": (
            "Update your CV — it hasn't been edited in over two months."
        ),
        "fill_core_sections": (
            "Fill in more core sections (summary, education, skills) for completeness."
        ),
        "refresh_stale": (
            "This CV is stale — refresh it before applying."
        ),
        "next_create_cv": "Create a CV to see your fit for this job",
        "next_select_best_cv": "Use your best-matching CV for this job",
        "next_improve_cv": "Improve your CV before applying",
        "next_apply": "Apply to this job",
        "next_save_job": "Save this job for later",
        "next_compare": "Compare with similar roles",
    },
}


def _t(locale: str, key: str, **fmt: str) -> str:
    """Return a localized string; fall back to ``vi`` for unknown locales."""

    table = _STRINGS.get(locale, _STRINGS[_DEFAULT_LOCALE])
    template = table.get(key) or _STRINGS[_DEFAULT_LOCALE][key]
    return template.format(**fmt) if fmt else template


def _fit_label(score: int) -> str:
    for threshold, label in _FIT_LABEL_THRESHOLDS:
        if score >= threshold:
            return label
    return "weak_fit"


def _improvement_actions(result: dict | None, *, locale: str = _DEFAULT_LOCALE) -> list[str]:
    if result is None:
        return [_t(locale, "no_cv")]

    actions: list[str] = []
    bands = result["bands"]
    if bands["skills"] < 70 and result["gaps"]:
        top_gaps = ", ".join(result["gaps"][:3])
        actions.append(_t(locale, "add_evidence", top_gaps=top_gaps))
    if bands["experience"] < 60:
        actions.append(_t(locale, "add_experience"))
    # Weak career-relevance signal: skills present but experience does not prove
    # them in the JD's field (the old standalone "domain" mismatch cue).
    if bands.get("experience", 100) < 45 and bands.get("skills", 0) >= 55:
        actions.append(_t(locale, "domain_mismatch"))
    if result["stale"]:
        actions.append(
            _t(locale, "update_cv_stale")
            if result["last_updated_days"] > 60
            else _t(locale, "refresh_stale")
        )
    return actions


def _present_fit(result: dict | None, *, signal: str, locale: str = _DEFAULT_LOCALE) -> dict:
    if result is None:
        return {
            "status": "no_active_cv",
            "score": None,
            "label": None,
            "bands": None,
            "matched_evidence": [],
            "gaps": [],
            "improvement_actions": _improvement_actions(None, locale=locale),
        }
    return {
        "status": "scored",
        "score": result["score"],
        "label": _fit_label(result["score"]),
        "bands": result["bands"],
        "matched_evidence": result["matched_skills"],
        "gaps": result["gaps"],
        "improvement_actions": _improvement_actions(result, locale=locale),
        "signal": signal,
        "stale": result["stale"],
        "explanation": result.get("explanation"),
    }


def _learning_gaps(result: dict | None, *, locale: str = _DEFAULT_LOCALE) -> list[dict]:
    if result is None or not result["gaps"]:
        return []
    gaps: list[dict] = []
    for gap in result["gaps"][:5]:
        # Curated skill -> resource mapping (specific resource_type + tailored,
        # localized suggestion); unknown skills fall back to the generic
        # ``practice_project`` resource. Deterministic and provider/model-free.
        resource = learning_resources.resource_for(gap, locale=locale)
        gaps.append({
            "skill": gap,
            "suggestion": resource["suggestion"],
            "resource_type": resource["resource_type"],
        })
    return gaps


def _next_actions(
    *,
    best_cv_id: str | None,
    selected_cv_id: str | None,
    has_active_cv: bool,
    fit_result: dict | None,
    apply_readiness: dict,
    locale: str = _DEFAULT_LOCALE,
) -> list[dict]:
    actions: list[dict] = []
    if not has_active_cv:
        actions.append({
            "action": "improve_cv",
            "label": _t(locale, "next_create_cv"),
        })
    else:
        if best_cv_id and best_cv_id != selected_cv_id:
            actions.append({
                "action": "select_best_cv",
                "cv_id": best_cv_id,
                "label": _t(locale, "next_select_best_cv"),
            })
        if fit_result and (fit_result["bands"]["skills"] < 70 or fit_result["stale"]):
            actions.append({
                "action": "improve_cv",
                "cv_id": selected_cv_id or best_cv_id,
                "label": _t(locale, "next_improve_cv"),
            })

    actions.append({
        "action": "apply",
        "label": _t(locale, "next_apply"),
        "ready": apply_readiness["ready"],
        "blocked_reason": apply_readiness["blocked_reason"],
    })
    actions.append({"action": "save_job", "label": _t(locale, "next_save_job")})
    actions.append({
        "action": "compare_adjacent_roles",
        "label": _t(locale, "next_compare"),
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
    locale: str = _DEFAULT_LOCALE,
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

    # ``with_explanation=False`` (the fast, deterministic-only path): the LLM is
    # NOT invoked here so this endpoint returns immediately. The AI explanation is
    # loaded separately by the frontend via ``GET /jobs/{job_id}/fit-explanation``
    # (``job_fit_service.fit_explanation_for_job``).
    fit_payload = await job_fit_service.job_fit_for_job(
        session, principal=principal, job_id=job_id, with_explanation=False
    )
    results = fit_payload["results"]
    by_id = {r["cv_id"]: r for r in results}
    best_cv_id = fit_payload["recommended_cv_id"]

    selected_cv_id = str(cv_id) if cv_id and str(cv_id) in by_id else None
    selected_result = by_id.get(selected_cv_id) if selected_cv_id else by_id.get(best_cv_id)

    fit = _present_fit(selected_result, signal=fit_payload["signal"], locale=locale)

    competition = await competition_service.student_competition_intelligence(
        session,
        principal=principal,
        job_id=job_id,
        student_fit_score=selected_result["score"] if selected_result else None,
        locale=locale,
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
        fit_result=selected_result,
        apply_readiness=apply_readiness,
        locale=locale,
    )

    return {
        "job_id": str(job_id),
        "selected_cv_id": selected_cv_id,
        "best_cv_id": best_cv_id,
        "fit": fit,
        "competition": competition,
        "learning_gaps": _learning_gaps(selected_result, locale=locale),
        "apply_readiness": apply_readiness,
        "next_actions": next_actions,
    }

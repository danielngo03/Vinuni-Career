"""On-demand HR CV↔JD evaluation — the partner "AI evaluate this candidate" action.

Builds on the EXISTING candidate-screening AI task (``screening_brief`` family +
the ``ai_recruiting.screen_candidate`` capability): the model acts as an
experienced recruiter producing a CATEGORICAL verdict of how well ONE
application's IMMUTABLE CV snapshot matches the job it was submitted to.

Contract (``docs/PARTNER_RBAC_ANALYTICS_SPEC.md`` + coordinator refinements
2026-07-10):

- RBAC: ``ai_recruiting:screen_candidate`` on the application's org (cross-org →
  404, non-enumerable). Every run is audited (actor / application / snapshot /
  JD version).
- Grounding: the DETERMINISTIC CV-JD fit signals (match score + matched/missing
  skills) + the CV snapshot's structured sections + the JD. The headline is the
  CATEGORICAL recommendation; the deterministic match score is the number.
- Metered: one governed gateway call with a partner ``UsageContext`` (budget
  pre-check + durable idempotent ledger). Re-opening the modal returns the STORED
  verdict with no re-spend; ``?refresh=true`` recomputes and re-meters.
- Guardrails: instruction-strip CV text (gateway input guard), bias guard on the
  output (no protected-attribute commentary), gaps framed "not evidenced", never
  fabricate, never expose provider/model/token/latency/prompt internals.
- Deterministic fallback when AI is down / over budget: a rules-based verdict from
  the deterministic fit (strengths = matched skills, gaps = missing required
  skills, recommendation from the band). Never 500, never fabricate.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import runtime_config
from app.ai.gateway.base import AIMessage
from app.ai.gateway.task_runner import AiTaskRunner
from app.ai.observability import billable_usage
from app.ai.prompts.screening_brief import v2 as eval_prompt
from app.ai.safety.bias_detection import check_bias
from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import application_fit_service, snapshot_service
from app.modules.opportunities.application import job_fit_read
from app.modules.recruitment.application import _shared
from app.modules.recruitment.domain.models import Application, CvEvaluation
from app.shared.audit import write_audit
from app.shared.exceptions import (
    AIUnavailableError,
    PaymentRequiredError,
    ResourceNotFoundError,
)
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "ai_recruiting"
_PERM_SCREEN = "screen_candidate"
_TASK_TYPE = "screening_brief"  # reuse the existing screening task identity
_FEATURE = billable_usage.FEATURE_SCREENING_BRIEF

_VALID_RECOMMENDATIONS = ("strong", "consider", "weak")
_VALID_VERDICTS = ("met", "partial", "not_evidenced")
# Deterministic band (fit engine) -> categorical recommendation.
_BAND_TO_RECOMMENDATION = {
    "strong": "strong",
    "good": "consider",
    "fair": "consider",
    "weak": "weak",
}
_MAX_TOKENS = 900


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #


async def evaluate_candidate_cv(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    ctx: RequestContext,
    refresh: bool = False,
    locale: str = "vi",
) -> dict:
    """Produce (or return the cached) HR verdict for an application's CV vs its JD."""

    app = await _shared.load_application(session, application_id=application_id)
    # Tenant isolation: a cross-org application is indistinguishable from missing.
    if not principal.is_superadmin and (
        principal.org_id is None or principal.org_id != app.org_id
    ):
        raise ResourceNotFoundError()
    # RBAC: the AI screening capability (advisory recruiting AI action).
    permission_checker.require(principal, _RESOURCE, _PERM_SCREEN, resource_org_id=app.org_id)

    if app.snapshot_id is None:
        # Nothing to evaluate (application carries no CV snapshot).
        raise ResourceNotFoundError()

    job_version = await _job_version(session, job_id=app.job_id)

    # Deterministic fit signals ground the LLM AND drive the fallback.
    signals = await application_fit_service.application_snapshot_fit_signals(
        session, snapshot_id=app.snapshot_id, job_id=app.job_id, locale=locale
    )

    # 1) Cache hit — return the stored (real, non-fallback) verdict with no re-spend.
    if not refresh:
        cached = await _load_cache(
            session, snapshot_id=app.snapshot_id, job_id=app.job_id
        )
        if (
            cached is not None
            and cached.job_version == job_version
            and not cached.is_fallback
        ):
            return _shape_response(
                dict(cached.result_json or {}),
                signals=signals,
                is_fallback=False,
                cached=True,
            )

    # 2) Compute: metered gateway call, else deterministic fallback.
    verdict, is_fallback = await _compute_verdict(
        session,
        app=app,
        principal=principal,
        signals=signals,
        job_version=job_version,
        refresh=refresh,
        locale=locale,
    )

    # Real verdicts are cached (version-stamped); fallbacks are NOT cached so a
    # later request retries the model once AI/budget recovers.
    if not is_fallback:
        await _store_cache(
            session,
            app=app,
            job_version=job_version,
            verdict=verdict,
            deterministic_score=(signals or {}).get("score"),
            actor_id=principal.user_id,
        )

    await write_audit(
        session,
        action="application.cv_evaluated",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "snapshot_id": str(app.snapshot_id),
            "job_id": str(app.job_id),
            "job_version": job_version,
            "recommendation": verdict.get("recommendation"),
            "is_fallback": is_fallback,
            "refresh": refresh,
        },
    )
    await session.commit()
    return _shape_response(
        verdict, signals=signals, is_fallback=is_fallback, cached=False
    )


# --------------------------------------------------------------------------- #
# Compute (model call + parse/guard) with deterministic fallback              #
# --------------------------------------------------------------------------- #


async def _compute_verdict(
    session: AsyncSession,
    *,
    app: Application,
    principal: Principal,
    signals: dict | None,
    job_version: int,
    refresh: bool,
    locale: str,
) -> tuple[dict, bool]:
    """Return ``(verdict, is_fallback)``. Never raises for a model/budget failure."""

    job = await job_fit_read.load_job_requirements(session, job_id=app.job_id)
    snapshot_json = (
        await snapshot_service.get_snapshot_json_for_application(
            session, application_id=app.id
        )
        or {}
    )
    if job is None or not snapshot_json:
        return _deterministic_verdict(signals, locale=locale, reason="not_computable"), True

    user_message = eval_prompt.build_user_message(
        job_title=str(job.get("title") or "this role"),
        required_skills=list(job.get("required_skills") or [])[:15],
        preferred_skills=list(job.get("preferred_skills") or [])[:12],
        responsibilities=job.get("requirements") or job.get("description"),
        match_score=(signals or {}).get("score"),
        matched_skills=(signals or {}).get("matched_skills") or [],
        missing_skills=(signals or {}).get("gaps") or [],
        candidate_skills=_cv_skills(snapshot_json),
        experience_entries=_cv_experience(snapshot_json),
        education_summary=_cv_education(snapshot_json),
    )

    # Idempotency: a normal compute is charged at most once per JD version; a
    # ``refresh`` deliberately re-meters (no idempotency key).
    idem = (
        None
        if refresh
        else billable_usage.make_idempotency_key(
            _FEATURE, "cv_eval", app.snapshot_id, app.job_id, job_version
        )
    )
    usage_ctx = billable_usage.UsageContext(
        actor_persona=billable_usage.PERSONA_PARTNER,
        feature_key=_FEATURE,
        task_type=_TASK_TYPE,
        billing_scope=billable_usage.SCOPE_ORG,
        actor_user_id=principal.user_id,
        org_id=app.org_id,
        resource_type="application",
        resource_id=app.id,
        idempotency_key=idem,
    )

    try:
        raw_text = await _run_model(
            session,
            system_prompt=eval_prompt.STATIC_SYSTEM_PROMPT,
            user_message=user_message,
            usage_ctx=usage_ctx,
            user_id=principal.user_id,
            org_id=app.org_id,
        )
    except (AIUnavailableError, PaymentRequiredError):
        # AI down OR org AI budget exhausted -> useful rules-based verdict, never 500.
        return _deterministic_verdict(signals, locale=locale, reason="ai_unavailable"), True

    parsed = _parse_json(raw_text)
    if parsed is None:
        return _deterministic_verdict(signals, locale=locale, reason="ai_unavailable"), True

    verdict = _normalize_verdict(parsed, signals=signals)

    # Fairness guard: a fair, job-relevant verdict has no protected-attribute
    # phrasing. If the bias guard flags a likely-illegal-discrimination phrase,
    # discard the model output and fall back to the deterministic verdict.
    if check_bias(_verdict_text(verdict)).requires_human_review:
        return _deterministic_verdict(signals, locale=locale, reason="guarded"), True

    # Guarantee a durable, idempotent ledger row for the charged, successful,
    # user-visible result (the runner also settles via energy_service when it is
    # wired; this call is idempotent on the same key, so it never double-charges).
    try:
        await billable_usage.record_billable_usage(
            session,
            ctx=usage_ctx,
            result_status=billable_usage.RESULT_SUCCESS,
            base_units=1,
        )
    except Exception:  # noqa: BLE001 — accounting must never break the response
        pass

    return verdict, False


async def _run_model(
    session: AsyncSession,
    *,
    system_prompt: str,
    user_message: str,
    usage_ctx: billable_usage.UsageContext,
    user_id: uuid.UUID | None,
    org_id: uuid.UUID | None,
) -> str:
    """Single governed, metered gateway completion. Returns SCRUBBED model text.

    Isolated as a module-level function so tests can monkeypatch the model call
    without touching the RBAC / cache / audit orchestration around it.
    """

    runner = AiTaskRunner(
        session,
        alias=runtime_config.current().chat_model_alias,
        task_type=_TASK_TYPE,
        user_id=user_id,
        org_id=org_id,
        usage_context=usage_ctx,
        tool_class="read_only",
    )
    completion = await runner.complete(
        [
            AIMessage(role="system", content=system_prompt),
            AIMessage(role="user", content=user_message),
        ],
        temperature=0.2,
        max_tokens=_MAX_TOKENS,
    )
    return completion.text


# --------------------------------------------------------------------------- #
# Cache read/write                                                            #
# --------------------------------------------------------------------------- #


async def _job_version(session: AsyncSession, *, job_id: uuid.UUID) -> int:
    """The JD content-version stamp (drives cache invalidation on JD edits)."""

    proj = await job_fit_read.load_job_requirements(session, job_id=job_id)
    if proj is not None and isinstance(proj.get("version"), int):
        return int(proj["version"])
    return 1


async def _load_cache(
    session: AsyncSession, *, snapshot_id: uuid.UUID, job_id: uuid.UUID
) -> CvEvaluation | None:
    return (
        await session.execute(
            select(CvEvaluation).where(
                CvEvaluation.snapshot_id == snapshot_id,
                CvEvaluation.job_id == job_id,
                CvEvaluation.cv_version == 1,
            )
        )
    ).scalar_one_or_none()


async def _store_cache(
    session: AsyncSession,
    *,
    app: Application,
    job_version: int,
    verdict: dict,
    deterministic_score: int | None,
    actor_id: uuid.UUID | None,
) -> None:
    assert app.snapshot_id is not None
    row = await _load_cache(session, snapshot_id=app.snapshot_id, job_id=app.job_id)
    if row is None:
        row = CvEvaluation(
            application_id=app.id,
            snapshot_id=app.snapshot_id,
            job_id=app.job_id,
            org_id=app.org_id,
            cv_version=1,
        )
        session.add(row)
    row.job_version = job_version
    row.recommendation = str(verdict.get("recommendation") or "consider")
    overall = verdict.get("overall_score")
    row.overall_score = int(overall) if isinstance(overall, int) else None
    row.deterministic_score = (
        int(deterministic_score) if isinstance(deterministic_score, int) else None
    )
    row.result_json = verdict
    row.is_fallback = False
    row.created_by = actor_id
    await session.flush()


# --------------------------------------------------------------------------- #
# Verdict normalization + deterministic fallback                              #
# --------------------------------------------------------------------------- #


def _parse_json(raw: str) -> dict | None:
    import json
    import re

    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except (ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_verdict(raw: dict, *, signals: dict | None) -> dict:
    """Validate + clamp a raw LLM verdict into the safe response shape.

    Pure function — unknown recommendation/verdict enum values are neutralized
    (never passed through verbatim), numbers are clamped, and every free-text
    field is length-capped so a hallucinated blob can't be echoed.
    """

    det_score = (signals or {}).get("score")
    fallback_rec = _BAND_TO_RECOMMENDATION.get((signals or {}).get("band_key", "weak"), "consider")

    rec = raw.get("recommendation")
    if rec not in _VALID_RECOMMENDATIONS:
        rec = fallback_rec

    raw_score = raw.get("overall_score")
    score: int | None = det_score if isinstance(det_score, int) else None
    if isinstance(raw_score, int | float | str):
        try:
            score = max(0, min(100, int(raw_score)))
        except (TypeError, ValueError):
            pass

    strengths = _clean_points(raw.get("strengths"), "point", "evidence")
    gaps = _clean_points(raw.get("gaps"), "point", "why_it_matters")
    criteria = _clean_criteria(raw.get("criteria"))

    raw_next = raw.get("next_step")
    next_step = (
        str(raw_next)[:220].strip()
        if isinstance(raw_next, str) and raw_next.strip()
        else None
    )

    return {
        "recommendation": rec,
        "overall_score": score,
        "summary": str(raw.get("summary") or "")[:600].strip(),
        "strengths": strengths,
        "gaps": gaps,
        "criteria": criteria,
        "next_step": next_step,
    }


def _clean_points(raw: object, primary: str, secondary: str) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        point = str(item.get(primary) or "")[:220].strip()
        if not point:
            continue
        out.append(
            {
                "point": point,
                secondary: str(item.get(secondary) or "")[:220].strip(),
            }
        )
        if len(out) >= 4:
            break
    return out


def _clean_criteria(raw: object) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")[:80].strip()
        if not name:
            continue
        verdict = item.get("verdict")
        if verdict not in _VALID_VERDICTS:
            verdict = "partial"
        out.append(
            {
                "name": name,
                "verdict": verdict,
                "note": str(item.get("note") or "")[:220].strip(),
            }
        )
        if len(out) >= 4:
            break
    return out


def _deterministic_verdict(signals: dict | None, *, locale: str, reason: str) -> dict:
    """A rules-based verdict from the deterministic fit — the AI-unavailable path.

    Strengths = matched JD skills; gaps = required/preferred skills NOT evidenced;
    recommendation derived from the fit band. Fully structured (same shape as the
    LLM verdict) so the modal renders identically; never fabricates a fact.
    """

    vi = locale != "en"
    score = (signals or {}).get("score")
    band_key = (signals or {}).get("band_key", "weak")
    matched = list((signals or {}).get("matched_skills") or [])
    gaps = list((signals or {}).get("gaps") or [])
    rec = _BAND_TO_RECOMMENDATION.get(band_key, "weak")

    strengths = [
        {
            "point": (f"Hồ sơ thể hiện {s}" if vi else f"CV evidences {s}"),
            "evidence": s,
        }
        for s in matched[:4]
    ]
    gap_items = [
        {
            "point": (f"Chưa thấy bằng chứng về {g}" if vi else f"{g} not evidenced"),
            "why_it_matters": (
                "Nằm trong yêu cầu của công việc." if vi else "Listed in the job requirements."
            ),
        }
        for g in gaps[:4]
    ]
    if matched and not gaps:
        skills_verdict = "met"
    elif matched:
        skills_verdict = "partial"
    else:
        skills_verdict = "not_evidenced"

    if vi:
        summary = "Đánh giá tự động dựa trên mức độ khớp kỹ năng (AI tạm thời không khả dụng)."
        skills_name = "Kỹ năng yêu cầu"
    else:
        summary = "Automated read from skill match (AI temporarily unavailable)."
        skills_name = "Required skills"

    return {
        "recommendation": rec,
        "overall_score": score if isinstance(score, int) else None,
        "summary": summary,
        "strengths": strengths,
        "gaps": gap_items,
        "criteria": [
            {
                "name": skills_name,
                "verdict": skills_verdict,
                "note": (
                    ", ".join(matched[:6]) if matched else ("—" if not vi else "—")
                ),
            }
        ],
        "next_step": None,
        "_fallback_reason": reason,
    }


# --------------------------------------------------------------------------- #
# Response shaping + snapshot extraction                                       #
# --------------------------------------------------------------------------- #


def _shape_response(
    verdict: dict, *, signals: dict | None, is_fallback: bool, cached: bool
) -> dict:
    """The user-safe response. Recommendation is the headline; the deterministic
    match score is the number (the ring). No provider/model/token/prompt leakage."""

    fallback_reason = verdict.get("_fallback_reason")
    return {
        "recommendation": verdict.get("recommendation"),
        "overall_score": verdict.get("overall_score"),
        "summary": verdict.get("summary") or "",
        "strengths": verdict.get("strengths") or [],
        "gaps": verdict.get("gaps") or [],
        "criteria": verdict.get("criteria") or [],
        "next_step": verdict.get("next_step"),
        # The deterministic match ring (the authoritative number); ``None`` when the
        # JD carries too little signal to score.
        "match_score": (signals or {}).get("score"),
        "match_band": (signals or {}).get("band"),
        "is_fallback": is_fallback,
        "fallback_reason": fallback_reason if is_fallback else None,
        "cached": cached,
    }


def _verdict_text(verdict: dict) -> str:
    parts = [str(verdict.get("summary") or "")]
    for s in verdict.get("strengths") or []:
        parts.append(str(s.get("point") or ""))
        parts.append(str(s.get("evidence") or ""))
    for g in verdict.get("gaps") or []:
        parts.append(str(g.get("point") or ""))
        parts.append(str(g.get("why_it_matters") or ""))
    for c in verdict.get("criteria") or []:
        parts.append(str(c.get("note") or ""))
    return " ".join(p for p in parts if p)


def _cv_skills(snapshot_json: dict) -> list[str]:
    for section in snapshot_json.get("sections") or []:
        title = (section.get("title") or "").lower()
        if "skill" in title:
            items = (section.get("content_json") or section.get("content") or {}).get("items") or []
            return [
                str(item.get("name") or item.get("title") or item)
                for item in items
                if item
            ][:20]
    return []


def _cv_experience(snapshot_json: dict) -> list[str]:
    for section in snapshot_json.get("sections") or []:
        title = (section.get("title") or "").lower()
        if "experience" in title or "work" in title:
            items = (section.get("content_json") or section.get("content") or {}).get("items") or []
            out: list[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                role = item.get("title") or item.get("role") or item.get("position") or ""
                org = item.get("organization") or item.get("company") or item.get("employer") or ""
                period = item.get("timeframe") or item.get("period") or item.get("dates") or ""
                line = " · ".join(str(p) for p in (role, org, period) if p)
                if line:
                    out.append(line)
            return out[:6]
    return []


def _cv_education(snapshot_json: dict) -> str:
    for section in snapshot_json.get("sections") or []:
        title = (section.get("title") or "").lower()
        if "education" in title:
            items = (section.get("content_json") or section.get("content") or {}).get("items") or []
            if items and isinstance(items[0], dict):
                first = items[0]
                degree = first.get("degree") or ""
                school = first.get("institution") or first.get("school") or ""
                parts = [p for p in (degree, school) if p]
                return ", ".join(str(p) for p in parts)[:200]
    return ""

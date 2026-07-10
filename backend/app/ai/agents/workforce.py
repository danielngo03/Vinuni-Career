"""Public entrypoint for the workforce (multi-agent) pattern.

Other modules/routers should only ever import from here, never reach into
``coordinator``/``worker_tasks`` directly — this is the thin facade the rest
of the codebase depends on (``docs/AI_PRODUCT_SPEC.md`` §4.2).

Currently exposes exactly one real consumer: bulk screening-brief generation
for a partner reviewing many applicants on one job. See
``docs/IMPLEMENTATION_STATUS.md`` / the ai-engineer handoff for what is
deliberately NOT built yet (a second consumer, a real running Celery worker
process, and a scheduled TTL-sweep of old runs).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import coordinator
from app.shared.permissions import Principal


async def start_bulk_screening_brief_run(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID
) -> dict:
    """Kick off a workforce run that screens every (capped) applicant on a job.

    Returns immediately with ``{run_id, status, total_subtasks}`` — the caller
    polls ``get_workforce_run_status`` (or the
    ``GET /ai/workforce/runs/{run_id}`` route) for progress/results.
    """

    run = await coordinator.start_bulk_screening_run(session, principal=principal, job_id=job_id)
    return {
        "run_id": str(run.id),
        "status": run.status,
        "total_subtasks": len(run.subtask_keys_json),
    }


async def get_workforce_run_status(
    session: AsyncSession, *, principal: Principal, run_id: uuid.UUID
) -> dict:
    """Current status + (if terminal) aggregated results for a workforce run."""

    return await coordinator.get_run(session, principal=principal, run_id=run_id)


# --------------------------------------------------------------------------- #
# Student career brief (deep-analysis, deterministic-first)                    #
# --------------------------------------------------------------------------- #
#
# The second workforce consumer: a "career brief" that runs the deterministic
# CV-JD matcher across the student's WHOLE CV library against the top visible
# opportunities, folds in the resulting skill-gap signal, clusters the best
# matches into career-focus areas, and returns a ``career_brief`` render artifact.
# It is DETERMINISTIC-FIRST — every number/cluster/priority is computed from
# system data with no model call — and the LLM is used ONLY to polish the final
# narrative (behind ``real_provider_active`` with a deterministic offline
# fallback, so offline evals + tests never spend a token). The heavy matching is
# off the interactive hot path (spec §2). Background/Celery scheduling of this run
# is the same deferred item noted above; today it is computed on demand.

# Friendly labels for the deterministic industry classifier's cluster keys.
_INDUSTRY_LABELS: dict[str, dict[str, str]] = {
    "software_it": {"vi": "Phần mềm & CNTT", "en": "Software & IT"},
    "data_ai": {"vi": "Dữ liệu & AI", "en": "Data & AI"},
    "design_ux": {"vi": "Thiết kế & UX", "en": "Design & UX"},
    "healthcare": {"vi": "Y tế & Chăm sóc sức khỏe", "en": "Healthcare"},
    "finance_accounting": {"vi": "Tài chính & Kế toán", "en": "Finance & Accounting"},
    "marketing_sales": {"vi": "Marketing & Kinh doanh", "en": "Marketing & Sales"},
    "hr_admin": {"vi": "Nhân sự & Hành chính", "en": "HR & Admin"},
    "education": {"vi": "Giáo dục & Đào tạo", "en": "Education & Training"},
    "manufacturing_engineering": {"vi": "Sản xuất & Kỹ thuật", "en": "Manufacturing & Engineering"},
    "construction": {"vi": "Xây dựng", "en": "Construction"},
    "legal": {"vi": "Pháp lý", "en": "Legal"},
    "hospitality_tourism": {"vi": "Khách sạn & Du lịch", "en": "Hospitality & Tourism"},
    "logistics_supplychain": {"vi": "Logistics & Chuỗi cung ứng", "en": "Logistics & Supply chain"},
}


def _brief_band(score: int) -> str:
    if score >= 80:
        return "strong"
    if score >= 65:
        return "good"
    if score >= 50:
        return "fair"
    return "weak"


def _brief_uuid(raw: object) -> uuid.UUID | None:
    if raw in (None, ""):
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except (ValueError, AttributeError):
        return None


async def student_career_brief(
    session: AsyncSession,
    *,
    principal: Principal,
    focus_query: str | None = None,
    locale: str = "vi",
    job_limit: int = 12,
) -> dict:
    """Deterministic-first career brief with a ``career_brief`` render artifact.

    Scores the student's whole CV library against the top visible opportunities,
    clusters the best matches into career-focus areas, ranks the most impactful
    skill gaps, and writes a short narrative (deterministic offline; LLM-polished
    when a real provider is active). Never raises — always ``{"ok": bool, ...}``.
    """
    from app.ai.cv import job_fit
    from app.core.config import get_settings
    from app.modules.documents.application import cv_ranking_facade
    from app.modules.opportunities.application import job_fit_read, job_service

    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    lc = "en" if str(locale).lower().startswith("en") else "vi"

    try:
        cv_inputs = await cv_ranking_facade.build_cv_inputs(session, principal=principal)
    except Exception:  # noqa: BLE001 - owner/permission failure → no CVs
        cv_inputs = []
    if not cv_inputs:
        return {
            "ok": True,
            "empty": True,
            "message": (
                "Create or upload a CV first so I can analyse your career options."
                if lc == "en"
                else "Hãy tạo hoặc tải lên một CV trước để tôi phân tích lựa chọn nghề nghiệp."
            ),
        }

    q = (focus_query or "").strip() or None
    try:
        items, *_rest = await job_service.list_public_jobs(
            session, principal=principal, q=q, cursor=None, limit=job_limit, locale=lc
        )
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "tool_failed"}

    persona = principal.persona or "student"
    stale = int(get_settings().cv_stale_after_days)
    # (best_score, job_id, title, industry_key, gaps)
    scored: list[tuple[int, str, str, str | None, list[str]]] = []
    for item in items:
        job_uuid = _brief_uuid(item.get("id"))
        if job_uuid is None:
            continue
        job = await job_fit_read.load_job_for_fit(
            session, job_id=job_uuid, persona=persona, locale=lc
        )
        if job is None:
            continue
        outcome = job_fit.evaluate(job, cv_inputs, stale_days=stale)
        if not outcome.results:
            continue
        best = max(outcome.results, key=lambda f: f.score)
        # The deterministic industry classifier is the honest "career cluster"
        # signal (same taxonomy the matcher uses); private within app.ai.
        industry = job_fit._jd_industry(job, job_fit.resolve_requirements(job))
        scored.append(
            (
                best.score,
                str(job_uuid),
                job.get("title") or "",
                industry,
                [g for g in best.gaps if g],
            )
        )

    if not scored:
        return {
            "ok": True,
            "empty": True,
            "message": (
                "I couldn't find enough matching opportunities to build a brief yet."
                if lc == "en"
                else "Chưa đủ cơ hội phù hợp để lập bản phân tích nghề nghiệp."
            ),
        }

    scored.sort(key=lambda r: -r[0])
    top = scored[:6]

    # --- Focus clusters (group by industry, rank by count then avg score) ----- #
    clusters: dict[str, list[tuple[int, str]]] = {}
    for score, jid, _title, industry, _gaps in scored:
        if industry is None:
            continue
        clusters.setdefault(industry, []).append((score, jid))
    ranked_clusters = sorted(
        clusters.items(),
        key=lambda kv: (-len(kv[1]), -(sum(s for s, _ in kv[1]) / len(kv[1]))),
    )[:3]
    focus_clusters = []
    for industry, members in ranked_clusters:
        label = _INDUSTRY_LABELS.get(industry, {}).get(lc, industry.replace("_", " ").title())
        avg = round(sum(s for s, _ in members) / len(members))
        why = (
            f"{len(members)} matching roles, average fit {avg}."
            if lc == "en"
            else f"{len(members)} vị trí phù hợp, độ phù hợp trung bình {avg}."
        )
        focus_clusters.append(
            {"label": label, "why": why, "example_job_ids": [jid for _s, jid in members[:3]]}
        )

    # --- Top matches ---------------------------------------------------------- #
    top_matches = [
        {"job_id": jid, "title": title, "fit_band": _brief_band(score)}
        for score, jid, title, _industry, _gaps in top
    ]

    # --- Skill priorities (most frequent gaps across the top matches) --------- #
    gap_counts: dict[str, int] = {}
    gap_display: dict[str, str] = {}
    for _score, _jid, _title, _industry, gaps in top:
        for gap in gaps[:8]:
            key = gap.strip().lower()
            if not key:
                continue
            gap_counts[key] = gap_counts.get(key, 0) + 1
            gap_display.setdefault(key, gap.strip())
    skill_priorities = [
        {
            "skill": gap_display[key],
            "impact": "high" if count >= 2 else "medium",
        }
        for key, count in sorted(gap_counts.items(), key=lambda kv: -kv[1])[:5]
    ]

    summary = _career_brief_summary(focus_clusters, top_matches, skill_priorities, lc)
    summary = await _maybe_polish_narrative(session, principal, summary, focus_query, lc)

    return {
        "ok": True,
        "render": {
            "kind": "career_brief",
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "focus_clusters": focus_clusters,
            "top_matches": top_matches,
            "skill_priorities": skill_priorities,
            "summary": summary,
        },
    }


def _career_brief_summary(
    focus_clusters: list[dict],
    top_matches: list[dict],
    skill_priorities: list[dict],
    locale: str,
) -> str:
    """Deterministic narrative — the always-available baseline (no model call)."""
    top_cluster = focus_clusters[0]["label"] if focus_clusters else None
    top_job = top_matches[0]["title"] if top_matches else None
    skills = ", ".join(p["skill"] for p in skill_priorities[:3])
    if locale == "en":
        parts = []
        if top_cluster:
            parts.append(f"Your strongest career direction right now is {top_cluster}.")
        if top_job:
            parts.append(f"The single best-matched role is “{top_job}”.")
        if skills:
            parts.append(f"Focus on building: {skills}.")
        return " ".join(parts) or "Here is your career overview."
    parts = []
    if top_cluster:
        parts.append(f"Hướng nghề nghiệp mạnh nhất của bạn hiện tại là {top_cluster}.")
    if top_job:
        parts.append(f"Vị trí phù hợp nhất là “{top_job}”.")
    if skills:
        parts.append(f"Nên tập trung phát triển: {skills}.")
    return " ".join(parts) or "Đây là tổng quan nghề nghiệp của bạn."


async def _maybe_polish_narrative(
    session: AsyncSession,
    principal: Principal,
    deterministic_summary: str,
    focus_query: str | None,
    locale: str,
) -> str:
    """LLM polish of the summary — behind the real-provider gate, offline-safe.

    Returns the deterministic summary unchanged when no real provider is active or
    on any failure, so tests + offline evals never spend a token. Output passes
    through the gateway's output guard (provider/model/token scrub) via the runner.
    """
    from app.ai.gateway.factory import real_provider_active

    if not real_provider_active():
        return deterministic_summary
    try:
        from app.ai.gateway import runtime_config
        from app.ai.gateway.base import AIMessage
        from app.ai.gateway.output_guard import scrub_text
        from app.ai.gateway.task_runner import AiTaskRunner
        from app.ai.safety.input_guard import sanitize_instruction

        safe_focus_raw, _ = sanitize_instruction(focus_query or "")
        safe_focus = safe_focus_raw or ""
        lang = "English" if locale == "en" else "Vietnamese"
        prompt = (
            "You are a concise university career advisor. Rewrite the following career "
            f"summary in natural {lang}, 2-3 sentences, encouraging and specific. Do not "
            "invent facts, jobs, or numbers beyond what is given. Do not mention being an "
            "AI, models, or tools.\n\n"
            f"Student focus (optional): {safe_focus[:200]}\n\nSummary: {deterministic_summary}"
        )
        runner = AiTaskRunner(
            session,
            alias=runtime_config.current().chat_model_alias,
            task_type="student_career_brief",
            user_id=principal.user_id,
            org_id=principal.org_id,
        )
        resp = await runner.complete(
            [AIMessage(role="user", content=prompt)], temperature=0.5, max_tokens=200
        )
        text = scrub_text(resp.text).strip()
        return text or deterministic_summary
    except Exception:  # noqa: BLE001 - narrative polish is advisory; never fatal
        return deterministic_summary

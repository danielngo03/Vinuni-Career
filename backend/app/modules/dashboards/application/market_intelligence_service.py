"""Market intelligence read model (AI_PRODUCT_SPEC §3 ``market_intelligence``).

University-staff-only (``restricted_admin`` in product terms → the same
university gate as the university dashboard). Aggregates come from the
opportunities module's application facade (``job_read_facade.market_aggregates``
— no cross-module ORM import) and are deterministic and always available. The
optional AI narrative is enrichment on top: when the gateway is unavailable
the response degrades to aggregates with ``ai_narrative_available: false``
(fallback per §3: "scheduled SQL reports" / aggregates without narrative).

Privacy: aggregates only. No student, application, or per-person data ever
enters the prompt; partner names are not included (counts only).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv.llm import generate_note
from app.ai.prompts.market_intelligence import v1 as mi_prompt
from app.modules.dashboards.application.university_dashboard import (
    _require_university,
)
from app.shared.permissions import Principal

_TASK_TYPE = "market_intelligence"
_MAX_TOKENS = 400


def _clean_counts(raw: dict) -> dict[str, int]:
    """Keep only string keys with numeric counts — garbage never crashes."""
    clean: dict[str, int] = {}
    for key, value in (raw or {}).items():
        if not isinstance(key, str) or not key.strip():
            continue
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        clean[key] = int(value)
    return clean


def build_report(
    *,
    active_jobs: int,
    jobs_last_30d: int,
    jobs_prev_30d: int,
    employment_type_counts: dict[str, int],
    skill_counts: dict[str, int],
    disclosed_salary_jobs: int,
) -> dict:
    """Compose the aggregate report — pure and deterministic (eval-friendly)."""
    employment_type_counts = _clean_counts(employment_type_counts)
    skill_counts = _clean_counts(skill_counts)
    if jobs_last_30d > jobs_prev_30d:
        trend = "up"
    elif jobs_last_30d < jobs_prev_30d:
        trend = "down"
    else:
        trend = "flat"

    disclosure_rate = round(100 * disclosed_salary_jobs / active_jobs) if active_jobs else 0
    return {
        "active_jobs": active_jobs,
        "jobs_last_30d": jobs_last_30d,
        "jobs_prev_30d": jobs_prev_30d,
        "trend": trend,
        "employment_types": [
            {"type": t, "count": c}
            for t, c in sorted(employment_type_counts.items(), key=lambda kv: -kv[1])[:5]
        ],
        "top_skills": [
            {"skill": s, "count": c}
            for s, c in sorted(skill_counts.items(), key=lambda kv: -kv[1])[:10]
        ],
        "salary_disclosure_rate": disclosure_rate,
        "low_signal": active_jobs < 5,
    }


async def narrate_report(report: dict) -> str | None:
    """AI narrative over the aggregate report; ``None`` on gateway failure."""
    try:
        return await generate_note(
            task_type=_TASK_TYPE,
            system_prompt=mi_prompt.STATIC_SYSTEM_PROMPT,
            user_content=mi_prompt.build_user_message(report),
            temperature=0.3,
            max_tokens=_MAX_TOKENS,
        )
    except Exception:  # noqa: BLE001 — AI enrichment degrades, never breaks
        return None


async def get_market_intelligence(
    session: AsyncSession,
    *,
    principal: Principal,
    include_narrative: bool = True,
) -> dict:
    await _require_university(session, principal)

    # Local import: avoids a snapshot_service <-> market_intelligence_service
    # cycle (snapshot_service calls back into ``build_report`` here).
    from app.modules.dashboards.application import snapshot_service

    report = await snapshot_service.read_for_display(session)

    narrative: str | None = None
    if include_narrative and not report["low_signal"]:
        narrative = await narrate_report(report)

    return {
        **report,
        "ai_narrative": narrative,
        "ai_narrative_available": narrative is not None,
    }

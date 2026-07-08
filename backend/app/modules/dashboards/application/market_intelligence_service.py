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
from app.ai.energy import service as energy_service
from app.ai.energy.constants import FEATURE_MARKET_INTELLIGENCE
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

    disclosure_rate = (
        round(100 * disclosed_salary_jobs / active_jobs) if active_jobs else 0
    )
    return {
        "active_jobs": active_jobs,
        "jobs_last_30d": jobs_last_30d,
        "jobs_prev_30d": jobs_prev_30d,
        "trend": trend,
        "employment_types": [
            {"type": t, "count": c}
            for t, c in sorted(
                employment_type_counts.items(), key=lambda kv: -kv[1]
            )[:5]
        ],
        "top_skills": [
            {"skill": s, "count": c}
            for s, c in sorted(skill_counts.items(), key=lambda kv: -kv[1])[:10]
        ],
        "salary_disclosure_rate": disclosure_rate,
        "low_signal": active_jobs < 5,
    }


async def narrate_report(
    report: dict,
    *,
    session: AsyncSession | None = None,
    principal: Principal | None = None,
) -> str | None:
    """AI narrative over the aggregate report; ``None`` on gateway failure.

    When ``session`` + ``principal`` are supplied (the product path) the call is
    metered through the governed gateway and debits the university org's energy
    ledger on success. Without them (the offline eval harness) it runs on the
    unmetered legacy path.
    """
    usage_context = energy_service.build_usage_context(
        principal,
        feature_key=FEATURE_MARKET_INTELLIGENCE,
        task_type=_TASK_TYPE,
    )
    try:
        # Gate ONLY the AI narrative on energy — the deterministic aggregates in
        # ``get_market_intelligence`` always render. Exhaustion raises here and is
        # caught below, degrading to "no narrative" rather than failing the report.
        if session is not None and principal is not None:
            await energy_service.enforce_energy(session, principal=principal)
        return await generate_note(
            task_type=_TASK_TYPE,
            system_prompt=mi_prompt.STATIC_SYSTEM_PROMPT,
            user_content=mi_prompt.build_user_message(report),
            temperature=0.3,
            max_tokens=_MAX_TOKENS,
            db=session,
            user_id=principal.user_id if principal else None,
            org_id=principal.org_id if principal else None,
            usage_context=usage_context,
            charge_units=energy_service.charge_units(FEATURE_MARKET_INTELLIGENCE),
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

    # NOTE: no endpoint-level energy gate — the deterministic aggregates must
    # survive AI-energy exhaustion (owner: non-AI paths always work). Only the
    # narrative in ``narrate_report`` is energy-gated and degrades to None.

    # Local import: avoids a snapshot_service <-> market_intelligence_service
    # cycle (snapshot_service calls back into ``build_report`` here).
    from app.modules.dashboards.application import snapshot_service

    report = await snapshot_service.read_for_display(session)

    narrative: str | None = None
    if include_narrative and not report["low_signal"]:
        narrative = await narrate_report(
            report, session=session, principal=principal
        )

    return {
        **report,
        "ai_narrative": narrative,
        "ai_narrative_available": narrative is not None,
    }

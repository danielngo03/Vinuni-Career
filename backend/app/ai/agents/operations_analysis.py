"""Second workforce consumer: university operations deep-analysis (§4.2 / WS3.4).

A granted university staffer starts a bounded, READ-ONLY multi-agent analysis on
a concrete target. The first (and today only) target is a partner employer's
**hiring quality** (``partner_hiring_quality``).

Shape (mirrors the bulk-screening consumer's coordinator → workers → aggregate
structure, reusing the same ``ai_workforce_runs`` run/status model):

  coordinator            ``decompose_operations_analysis`` → 4 sub-passes
  sub-agents (Celery)    one idempotent subtask per pass, each a DETERMINISTIC
                         read over the owning module's application read-model /
                         facade (NO cross-module domain imports), escalating to a
                         cheap text-LLM narrative ONLY when a pass is
                         low-confidence ("many layers, save tokens")
  synthesis              ``synthesize_operations_report`` merges the sub-pass
                         findings into a structured, privacy-safe report

Every value in the report is a privacy-safe aggregate / band / label — never
another user's PII, never provider/model/token internals. The report is
ADVISORY; the run performs no consequential domain writes (read-only analysis).

RBAC: enforced ONCE at ``start_operations_analysis_run`` (superadmin, or a
university-org staffer holding ``partners:read``) — the same "check at plan time,
trust the reconstructed principal in the worker" model the bulk-screening
consumer uses — plus a pure defense-in-depth re-check inside each pass.

Metering: only a low-confidence pass that produces a *successful, parsed*
narrative debits the initiating user's energy ledger (idempotent per
``(run_id, area)``). Deterministic passes and failed/unavailable narratives cost
nothing.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import coordinator
from app.ai.agents.models import (
    RunStatus,
    SubtaskSpec,
    SubtaskStatus,
    WorkforceRun,
)
from app.ai.cv.llm import generate_json_note
from app.ai.energy import service as energy_service
from app.ai.energy.constants import FEATURE_OPERATIONS_ANALYSIS
from app.ai.prompts.operations_analysis import v1 as narrative_prompt
from app.shared.exceptions import (
    AIUnavailableError,
    AppError,
    AuthRequiredError,
    PermissionDeniedError,
    QuotaExceededError,
    ResourceNotFoundError,
)
from app.shared.permissions import Principal, permission_checker

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Task / target / pass vocabulary                                             #
# --------------------------------------------------------------------------- #

OPERATIONS_ANALYSIS_TASK_TYPE = "operations_analysis"
OPERATIONS_PASS_SUBTASK_TYPE = "operations_analysis_pass"

# The one concrete, high-value target implemented (extend by adding a target +
# its reader set — never by branching an existing reader on target_type).
TARGET_PARTNER_HIRING_QUALITY = "partner_hiring_quality"
SUPPORTED_TARGETS = frozenset({TARGET_PARTNER_HIRING_QUALITY})

# Fixed, deterministic sub-pass set for the partner-hiring-quality target. Each
# is one idempotent subtask keyed by its own name.
OPS_PASSES: tuple[str, ...] = (
    "jobs_quality",
    "pipeline_health",
    "outcomes",
    "compliance_flags",
)

# Narrative scrubbing: a grounded rephrase must never carry these (defense in
# depth on top of the gateway output guard).
_BANNED_NARRATIVE_TOKENS = (
    "openai",
    "anthropic",
    "gpt-",
    "claude",
    "deepseek",
    "gemini",
    "llama",
    "api_key",
    "model_alias",
    "prompt_tokens",
)


# --------------------------------------------------------------------------- #
# Decomposition (pure)                                                        #
# --------------------------------------------------------------------------- #


def decompose_operations_analysis(
    *, run_id: uuid.UUID, target_type: str, target_org_id: uuid.UUID
) -> list[SubtaskSpec]:
    """One subtask per fixed sub-pass. Deterministic key -> safe to retry."""

    return [
        SubtaskSpec(
            key=pass_name,
            subtask_type=OPERATIONS_PASS_SUBTASK_TYPE,
            payload={
                "pass": pass_name,
                "target_type": target_type,
                "target_org_id": str(target_org_id),
                "run_id": str(run_id),
            },
        )
        for pass_name in OPS_PASSES
    ]


# --------------------------------------------------------------------------- #
# Deterministic read passes (owning-module application read-models only)      #
# --------------------------------------------------------------------------- #


def _confidence(*, value: int, low_below: int, high_at: int) -> str:
    if value < low_below:
        return "low"
    if value >= high_at:
        return "high"
    return "medium"


async def _read_jobs_quality(session: AsyncSession, org_id: uuid.UUID) -> dict:
    """JD hygiene signals from ``opportunities`` job read facade (counts only)."""

    from app.modules.opportunities.application import job_read_facade

    refs = await job_read_facade.list_org_job_refs(session, org_id=org_id)
    buckets = {
        "active": 0,
        "pending_review": 0,
        "rejected": 0,
        "draft": 0,
        "closed": 0,
        "other": 0,
    }
    missing_deadline = 0
    for ref in refs:
        status = ref.status if ref.status in buckets else "other"
        buckets[status] += 1
        if ref.application_deadline is None:
            missing_deadline += 1
    total = len(refs)
    signals = {
        "total_jobs": total,
        "by_status": buckets,
        "with_deadline": total - missing_deadline,
        "missing_deadline": missing_deadline,
    }
    return {
        "area": "jobs_quality",
        "signals": signals,
        "confidence": _confidence(value=total, low_below=3, high_at=10),
    }


async def _read_pipeline_health(session: AsyncSession, org_id: uuid.UUID) -> dict:
    """Application-volume / hire signals from ``recruitment`` read-model (no PII)."""

    from app.modules.recruitment.application import dashboard_read

    funnel = await dashboard_read.analytics_application_funnel(session, org_id=org_id)
    outcomes = await dashboard_read.hiring_outcomes_for_org(session, org_id=org_id)
    total_apps = int(outcomes.get("total_applications", 0) or 0)
    signals = {
        "total_applications": total_apps,
        "funnel": funnel,
        "hired": int(outcomes.get("hired", 0) or 0),
        "offers_accepted": int(outcomes.get("offers_accepted", 0) or 0),
        "recent_applications": int(outcomes.get("recent_applications", 0) or 0),
    }
    return {
        "area": "pipeline_health",
        "signals": signals,
        "confidence": _confidence(value=total_apps, low_below=5, high_at=20),
    }


async def _read_outcomes(session: AsyncSession, org_id: uuid.UUID) -> dict:
    """Graduate-outcome mix for this employer from ``career_outcomes`` (aggregate)."""

    from app.modules.career_outcomes.application import read_service as co_read_service

    agg = await co_read_service.employer_outcomes_aggregate(
        session, employer_org_id=org_id
    )
    total = int(agg.get("total_outcomes", 0) or 0)
    return {
        "area": "outcomes",
        "signals": agg,
        "confidence": _confidence(value=total, low_below=1, high_at=5),
    }


async def _read_compliance_flags(session: AsyncSession, org_id: uuid.UUID) -> dict:
    """Moderation-friction signals from job statuses + coarse application funnel."""

    from app.modules.opportunities.application import job_read_facade
    from app.modules.recruitment.application import dashboard_read

    refs = await job_read_facade.list_org_job_refs(session, org_id=org_id)
    total = len(refs)
    jobs_sent_back = sum(1 for r in refs if r.status == "rejected")
    jobs_pending = sum(1 for r in refs if r.status == "pending_review")
    funnel = await dashboard_read.analytics_application_funnel(session, org_id=org_id)
    by_status = {row["status"]: int(row["count"]) for row in funnel}
    rate = round(jobs_sent_back / total, 2) if total else 0.0
    signals = {
        "total_jobs": total,
        "jobs_sent_back": jobs_sent_back,
        "jobs_pending_review": jobs_pending,
        "moderation_flag_rate": rate,
        "rejected_applications": by_status.get("rejected", 0),
        "withdrawn_applications": by_status.get("withdrawn", 0),
    }
    return {
        "area": "compliance_flags",
        "signals": signals,
        "confidence": _confidence(value=total, low_below=3, high_at=10),
    }


_READERS = {
    "jobs_quality": _read_jobs_quality,
    "pipeline_health": _read_pipeline_health,
    "outcomes": _read_outcomes,
    "compliance_flags": _read_compliance_flags,
}


# --------------------------------------------------------------------------- #
# Cheap narrative escalation (metered; low-confidence passes only)            #
# --------------------------------------------------------------------------- #


def _clean_narrative(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    cleaned = text.strip()[:300]
    lowered = cleaned.lower()
    if any(tok in lowered for tok in _BANNED_NARRATIVE_TOKENS):
        return None
    return cleaned or None


async def _maybe_narrate(
    session: AsyncSession, principal: Principal, *, payload: dict, pass_result: dict
) -> dict:
    """Add a grounded 1-2 sentence narrative ONLY for a low-confidence pass.

    Deterministic passes (medium/high confidence) return unchanged with no model
    call. On AI-off / exhausted energy / any failure the narrative is omitted and
    marked (never fabricated) — the deterministic signals always remain.
    """

    result = dict(pass_result)
    result["narrative"] = None
    result["narrative_available"] = False
    if result.get("confidence") != "low":
        return result

    area = result.get("area", payload.get("pass", ""))
    signals = result.get("signals") or {}
    run_id = payload.get("run_id")
    try:
        await energy_service.enforce_energy(session, principal=principal)
        usage_context = energy_service.build_usage_context(
            principal,
            feature_key=FEATURE_OPERATIONS_ANALYSIS,
            task_type=OPERATIONS_ANALYSIS_TASK_TYPE,
            resource_type="operations_analysis",
            resource_id=principal.org_id,
            idempotency_parts=(run_id, area) if run_id else None,
        )
        data = await generate_json_note(
            task_type=OPERATIONS_ANALYSIS_TASK_TYPE,
            system_prompt=narrative_prompt.STATIC_SYSTEM_PROMPT,
            user_content=narrative_prompt.build_user_message(area=area, signals=signals),
            temperature=0.2,
            max_tokens=180,
            db=session,
            user_id=principal.user_id,
            org_id=principal.org_id,
            usage_context=usage_context,
            charge_units=energy_service.charge_units(FEATURE_OPERATIONS_ANALYSIS),
        )
        narrative = _clean_narrative(data.get("narrative"))
        if narrative:
            result["narrative"] = narrative
            result["narrative_available"] = True
    except (AIUnavailableError, QuotaExceededError):
        # AI off / energy exhausted → deterministic-only, marked (never faked).
        return result
    except Exception:  # noqa: BLE001 - narrative is best-effort, must never crash a pass
        logger.warning(
            "operations_analysis.narrate_failed",
            extra={"area": area, "run_id": str(run_id)},
            exc_info=True,
        )
    return result


# --------------------------------------------------------------------------- #
# Sub-agent executor (registered on the workforce EXECUTORS table)            #
# --------------------------------------------------------------------------- #


def _may_analyze_partner(principal: Principal) -> bool:
    """Pure defense-in-depth: the run was already RBAC-gated at plan time."""

    if principal.is_superadmin:
        return True
    if not principal.is_authenticated:
        return False
    if not (principal.persona or "").startswith("university"):
        return False
    return permission_checker.can(principal, "partners", "read")


async def _execute_pass(
    session: AsyncSession, principal: Principal, payload: dict
) -> dict:
    """Run one deterministic read pass (+ optional low-confidence narrative)."""

    if not _may_analyze_partner(principal):
        raise PermissionDeniedError()
    pass_name = payload.get("pass")
    reader = _READERS.get(pass_name or "")
    target_org_id = _parse_uuid(payload.get("target_org_id"))
    if reader is None or target_org_id is None:
        raise ValueError("invalid operations-analysis payload")

    pass_result = await reader(session, target_org_id)
    pass_result = await _maybe_narrate(
        session, principal, payload=payload, pass_result=pass_result
    )
    pass_result["target_type"] = payload.get("target_type")
    return pass_result


# subtask_type -> executor. Registered into ``worker_tasks.EXECUTORS`` (a new
# executor entry, not a branch on an existing one — §4.2 extension rule).
OPS_EXECUTORS = {OPERATIONS_PASS_SUBTASK_TYPE: _execute_pass}


# --------------------------------------------------------------------------- #
# Synthesis (pure) — the aggregator the coordinator runs once all passes end  #
# --------------------------------------------------------------------------- #


def _deterministic_signal(area: str, s: dict) -> str:
    if area == "jobs_quality":
        return (
            f"{s.get('total_jobs', 0)} job posting(s); "
            f"{s.get('missing_deadline', 0)} without an application deadline."
        )
    if area == "pipeline_health":
        return (
            f"{s.get('total_applications', 0)} application(s), "
            f"{s.get('hired', 0)} hire(s), "
            f"{s.get('offers_accepted', 0)} accepted offer(s)."
        )
    if area == "outcomes":
        return f"{s.get('total_outcomes', 0)} recorded graduate outcome(s) for this employer."
    if area == "compliance_flags":
        return (
            f"{s.get('jobs_sent_back', 0)} job(s) sent back in moderation "
            f"(send-back rate {s.get('moderation_flag_rate', 0)})."
        )
    return "See aggregate signals."


def _recommendations(by_area: dict[str, dict]) -> list[str]:
    recs: list[str] = []
    jq = by_area.get("jobs_quality") or {}
    if jq.get("missing_deadline", 0) > 0:
        recs.append(
            f"{jq['missing_deadline']} job(s) have no application deadline — "
            "ask the partner to set clear deadlines."
        )
    ph = by_area.get("pipeline_health") or {}
    if ph.get("total_applications", 0) == 0 and jq.get("total_jobs", 0) > 0:
        recs.append(
            "This partner's roles have no applications yet — consider promotion "
            "or a JD review."
        )
    elif ph.get("total_applications", 0) > 0 and ph.get("hired", 0) == 0:
        recs.append(
            "Applications are flowing but no hires are recorded — check pipeline "
            "responsiveness with the partner."
        )
    cf = by_area.get("compliance_flags") or {}
    if cf.get("moderation_flag_rate", 0) and cf["moderation_flag_rate"] >= 0.3:
        recs.append(
            "Elevated moderation send-back rate — review this partner's "
            "job-posting quality."
        )
    oc = by_area.get("outcomes") or {}
    if oc.get("total_outcomes", 0) == 0:
        recs.append(
            "No graduate outcomes recorded for this employer — follow up on "
            "placement reporting."
        )
    return recs


def _summary(by_area: dict[str, dict], *, passes_ok: int, passes_total: int) -> str:
    jq = by_area.get("jobs_quality") or {}
    ph = by_area.get("pipeline_health") or {}
    oc = by_area.get("outcomes") or {}
    return (
        f"Reviewed {passes_ok}/{passes_total} areas of this partner's hiring "
        f"quality: {jq.get('total_jobs', 0)} job(s), "
        f"{ph.get('total_applications', 0)} application(s), "
        f"{ph.get('hired', 0)} hire(s), "
        f"{oc.get('total_outcomes', 0)} recorded outcome(s)."
    )


def synthesize_operations_report(subtask_results_json: dict) -> dict:
    """Merge sub-pass findings into a structured, privacy-safe report (pure).

    Shape: ``{target, summary, findings:[{area,signal,evidence}],
    recommendations:[...], caveats:[...], coverage:{...}}``. A failed/degraded
    pass yields a caveat and a partial report — never a fabricated finding.
    """

    findings: list[dict] = []
    caveats: list[str] = []
    signals_by_area: dict[str, dict] = {}
    passes_ok = 0
    passes_failed = 0
    narratives = 0

    for pass_name in OPS_PASSES:  # deterministic order
        entry = subtask_results_json.get(pass_name)
        if entry is None:
            continue  # not yet reported (in-progress) — omit, do not invent
        status = entry.get("status")
        result = entry.get("result") or {}
        if status == SubtaskStatus.SUCCESS.value and result:
            area = result.get("area", pass_name)
            signals = result.get("signals") or {}
            signals_by_area[area] = signals
            narrative = result.get("narrative")
            if narrative:
                narratives += 1
            findings.append(
                {
                    "area": area,
                    "signal": narrative or _deterministic_signal(area, signals),
                    "evidence": signals,
                }
            )
            passes_ok += 1
            if result.get("confidence") == "low" and not result.get(
                "narrative_available"
            ):
                caveats.append(
                    f"The {area.replace('_', ' ')} area has little data; "
                    "its findings are low-confidence."
                )
        else:
            passes_failed += 1
            caveats.append(
                f"The {pass_name.replace('_', ' ')} analysis could not be "
                "completed; this report is partial."
            )

    caveats.append(
        "Advisory only — figures are privacy-safe aggregates; a human makes all "
        "decisions."
    )
    return {
        "target": {"type": TARGET_PARTNER_HIRING_QUALITY},
        "summary": _summary(
            signals_by_area, passes_ok=passes_ok, passes_total=len(OPS_PASSES)
        ),
        "findings": findings,
        "recommendations": _recommendations(signals_by_area),
        "caveats": caveats,
        "coverage": {
            "passes_total": len(OPS_PASSES),
            "passes_ok": passes_ok,
            "passes_failed": passes_failed,
            "narratives": narratives,
        },
    }


# --------------------------------------------------------------------------- #
# Run lifecycle                                                               #
# --------------------------------------------------------------------------- #


def _parse_uuid(raw: object) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None


async def start_operations_analysis_run(
    session: AsyncSession,
    *,
    principal: Principal,
    target_type: str,
    target_org_id: uuid.UUID,
) -> WorkforceRun:
    """RBAC-gate, validate the target, plan the fan-out, persist + audit, dispatch.

    RBAC (service layer): superadmin, or a university-org staffer holding
    ``partners:read``. The target must resolve to a real partner org (else 404,
    no existence leak). Read-only + advisory — no consequential domain write.
    """

    from app.modules.analytics.application import ingestion_service as analytics
    from app.modules.organization.application import org_reporting_facade

    if not principal.is_authenticated:
        raise AuthRequiredError()
    if target_type not in SUPPORTED_TARGETS:
        raise AppError("unsupported_analysis_target")

    if not principal.is_superadmin:
        if not await org_reporting_facade.is_university_org(session, principal.org_id):
            raise PermissionDeniedError(details={"reason": "university_only"})
        permission_checker.require(principal, "partners", "read")

    # Target must be a partner org (cross-type / missing → 404, no leak).
    if await org_reporting_facade.org_type_for(session, target_org_id) != "partner":
        raise ResourceNotFoundError()

    run_id = uuid.uuid4()
    subtasks = decompose_operations_analysis(
        run_id=run_id, target_type=target_type, target_org_id=target_org_id
    )
    assert principal.user_id is not None
    run = WorkforceRun(
        id=run_id,
        task_type=OPERATIONS_ANALYSIS_TASK_TYPE,
        status=RunStatus.RUNNING.value,
        requested_by_user_id=principal.user_id,
        org_id=principal.org_id,
        context_json={
            "target_type": target_type,
            "target_org_id": str(target_org_id),
            "principal": coordinator._serialize_principal(principal),
        },
        subtask_keys_json=[s.key for s in subtasks],
        subtask_results_json={},
        summary_json=None,
    )
    session.add(run)
    await session.flush()

    # Audit (who / what target / when) — metadata-only, never breaks the run.
    await analytics.record_event_safe(
        session,
        event_type="ai.operations_analysis.started",
        aggregate_type="ai_workforce_run",
        aggregate_id=run_id,
        actor_id=principal.user_id,
        actor_type="university",
        properties={
            "target_type": target_type,
            "target_org_id": str(target_org_id),
            "passes": len(subtasks),
        },
    )
    await session.commit()

    logger.info(
        "operations_analysis.start",
        extra={"run_id": str(run_id), "passes": len(subtasks)},
    )

    from app.ai.agents import worker_tasks

    for subtask in subtasks:
        worker_tasks.dispatch_subtask(run_id=run_id, subtask=subtask)
    return run

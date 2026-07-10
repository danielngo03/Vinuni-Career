"""Deterministic partner recruiting-intelligence tools.

Three read-only tools that answer natural-language recruiting questions from the
existing recruitment / partner-analytics READ MODELS — no LLM call, no candidate
PII, org-scoped and RBAC-gated:

- :func:`job_stats` — per-job applicant / unreviewed / in-pipeline counts (reuses
  the ``owner_job_summary`` funnel signals: ``unreviewed_count`` /
  ``in_pipeline_count``) plus the org application funnel.
- :func:`pipeline_summary` — candidates-by-STAGE for one job (reuses the RBAC-gated
  ``pipeline_board`` read model for human-readable stage names). Returns a
  chart-ready ``render`` artifact.
- :func:`recruiting_analytics` — answers a metric question (conversion /
  time-to-fill / source-mix) from the recruiting read models and returns
  chart-ready data using the Phase C chart contract.

Every handler re-checks org scope + capability at the service layer (the
real-time/tool path must not rely on native_loop's authorize pre-filter alone).
No provider/model/token internals ever appear — these tools never call a model.
"""

from __future__ import annotations

import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.permissions import Principal, permission_checker

# Human labels for the coarse recruiting-funnel steps (enum codes never reach the
# user — .claude/rules/ai.md).
_FUNNEL_LABELS: dict[str, dict[str, str]] = {
    "applied": {"vi": "Đã ứng tuyển", "en": "Applied"},
    "screened": {"vi": "Đã sàng lọc", "en": "Screened"},
    "interview": {"vi": "Phỏng vấn", "en": "Interview"},
    "offer": {"vi": "Đề nghị", "en": "Offer"},
    "hired": {"vi": "Đã tuyển", "en": "Hired"},
}

_SOURCE_LABELS: dict[str, dict[str, str]] = {
    "organic": {"vi": "Tự nhiên", "en": "Organic"},
    "search": {"vi": "Tìm kiếm", "en": "Search"},
    "recommendation": {"vi": "Gợi ý", "en": "Recommendation"},
    "sponsored": {"vi": "Tài trợ", "en": "Sponsored"},
    "invitation": {"vi": "Lời mời", "en": "Invitation"},
    "direct": {"vi": "Trực tiếp", "en": "Direct"},
}

_STAGE_TYPE_LABELS: dict[str, dict[str, str]] = {
    "screening": {"vi": "Sàng lọc", "en": "Screening"},
    "interview": {"vi": "Phỏng vấn", "en": "Interview"},
    "assessment": {"vi": "Đánh giá", "en": "Assessment"},
    "offer": {"vi": "Đề nghị", "en": "Offer"},
    "hired": {"vi": "Đã tuyển", "en": "Hired"},
}

_VALID_METRICS = frozenset({"conversion", "time_to_fill", "source_mix"})


def _loc(locale) -> str:
    return "en" if str(locale or "vi").lower().startswith("en") else "vi"


def _label(table: dict[str, dict[str, str]], key: str, locale: str) -> str:
    entry = table.get(key)
    return entry[locale] if entry else key.replace("_", " ").title()


def _parse_uuid(raw) -> _uuid.UUID | None:
    if not raw:
        return None
    try:
        return _uuid.UUID(str(raw).strip())
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# job_stats                                                                    #
# --------------------------------------------------------------------------- #


async def job_stats(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Per-job applicant / unreviewed / in-pipeline counts + the org funnel.

    Reuses ``job_service.list_my_jobs`` (RBAC-gated ``jobs:read``) which batches
    the live ``unreviewed_count`` / ``in_pipeline_count`` funnel signals per job.
    """
    from app.modules.opportunities.application import job_service

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}
    if not permission_checker.can(
        principal, "applications", "read", resource_org_id=principal.org_id
    ):
        return {"ok": False, "error": "permission_denied"}

    status_filter = (args.get("status") or "").strip() or None
    job_id = _parse_uuid(args.get("job_id"))

    try:
        items, _next, _limit = await job_service.list_my_jobs(
            session, principal=principal, status=status_filter, cursor=None, limit=25
        )
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "tool_failed"}

    rows = []
    for j in items or []:
        jid = str(j.get("id", ""))
        if job_id is not None and jid != str(job_id):
            continue
        rows.append(
            {
                "job_id": jid,
                "title": j.get("title", ""),
                "status": j.get("status_label") or j.get("status", ""),
                "applicants": j.get("application_count", 0) or 0,
                # ``None`` (not fabricated 0) when the funnel signal is unavailable.
                "unreviewed": j.get("unreviewed_count"),
                "in_pipeline": j.get("in_pipeline_count"),
                "deadline": j.get("application_deadline"),
                "url": f"/partner/jobs/{jid}",
            }
        )

    if job_id is not None and not rows:
        return {"ok": False, "error": "not_found"}

    totals = {
        "applicants": sum(r["applicants"] for r in rows),
        "unreviewed": sum(r["unreviewed"] or 0 for r in rows),
        "in_pipeline": sum(r["in_pipeline"] or 0 for r in rows),
        "job_count": len(rows),
    }

    return {
        "ok": True,
        "jobs": rows[:15],
        "totals": totals,
    }


# --------------------------------------------------------------------------- #
# pipeline_summary                                                            #
# --------------------------------------------------------------------------- #


async def pipeline_summary(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Candidates-by-STAGE for one job (RBAC-gated), with a chart-ready render.

    Reuses ``pipeline_board.get_job_pipeline_board`` — its ``_load_org_scoped_job``
    404s a cross-org job (tenant isolation) and enforces ``jobs:read`` — then
    strips all candidate PII, returning only stage NAME + COUNT.
    """
    from app.modules.recruitment.application import pipeline_board

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}
    if not permission_checker.can(
        principal, "applications", "read", resource_org_id=principal.org_id
    ):
        return {"ok": False, "error": "permission_denied"}

    job_id = _parse_uuid(args.get("job_id"))
    if job_id is None:
        return {"ok": False, "error": "job_id_required"}
    locale = _loc(args.get("locale"))

    try:
        board = await pipeline_board.get_job_pipeline_board(
            session, principal=principal, job_id=job_id, locale=locale
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "tool_failed"}

    columns = board.get("columns") or []
    stages = [
        {
            "name": col.get("name", ""),
            "count": int(col.get("count", 0) or 0),
            "stage_type": col.get("stage_type"),
        }
        for col in columns
    ]
    total_active = sum(s["count"] for s in stages)
    job = board.get("job") or {}
    title = job.get("title", "")

    result: dict = {
        "ok": True,
        "job_id": str(job_id),
        "job_title": title,
        "stages": stages,
        "total_active": total_active,
    }
    if total_active > 0:
        result["render"] = {
            "kind": "chart",
            "chart": {
                "type": "bar",
                "title": f"Pipeline — {title}",
                "x_key": "label",
                "series": [
                    {"key": "value", "name": "Ứng viên" if locale == "vi" else "Candidates"}
                ],
                "data": [{"label": s["name"], "value": s["count"]} for s in stages],
            },
        }
    else:
        result["empty"] = True
    return result


# --------------------------------------------------------------------------- #
# recruiting_analytics                                                        #
# --------------------------------------------------------------------------- #


async def recruiting_analytics(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Answer a recruiting-metric question with chart-ready data (no LLM).

    ``metric`` ∈ {conversion, time_to_fill, source_mix}. Every branch reads only
    aggregate, org-scoped read models — no candidate PII, no model call.
    Gated on ``analytics:view_job_metrics`` (the recruiting-analytics capability,
    independent of raw ``applications:read`` per the RBAC catalog).
    """
    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}
    if not permission_checker.can(
        principal, "analytics", "view_job_metrics", resource_org_id=principal.org_id
    ):
        return {"ok": False, "error": "permission_denied"}

    metric = (args.get("metric") or "conversion").strip().lower()
    if metric not in _VALID_METRICS:
        return {"ok": False, "error": "unknown_metric", "valid": sorted(_VALID_METRICS)}
    locale = _loc(args.get("locale"))
    org_id = principal.org_id

    try:
        if metric == "conversion":
            return await _conversion(session, org_id=org_id, locale=locale)
        if metric == "time_to_fill":
            return await _time_to_fill(session, org_id=org_id, locale=locale)
        return await _source_mix(session, org_id=org_id, locale=locale)
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "tool_failed"}


async def _conversion(session: AsyncSession, *, org_id: _uuid.UUID, locale: str) -> dict:
    from app.modules.recruitment.application import dashboard_read as rr

    counts = await rr.recruiting_funnel_counts(session, org_id=org_id)
    order = ["applied", "screened", "interview", "offer", "hired"]
    data = [{"label": _label(_FUNNEL_LABELS, k, locale), "value": counts.get(k, 0)} for k in order]
    applied = counts.get("applied", 0)
    hired = counts.get("hired", 0)
    if applied <= 0:
        return {
            "ok": True,
            "metric": "conversion",
            "empty": True,
            "title": "Tỷ lệ chuyển đổi" if locale == "vi" else "Conversion funnel",
        }
    overall_pct = round(100 * hired / applied, 1)
    title = "Tỷ lệ chuyển đổi tuyển dụng" if locale == "vi" else "Recruiting conversion funnel"
    return {
        "ok": True,
        "metric": "conversion",
        "title": title,
        "counts": counts,
        "applied": applied,
        "hired": hired,
        "overall_conversion_pct": overall_pct,
        "render": {
            "kind": "chart",
            "chart": {
                "type": "bar",
                "title": title,
                "x_key": "label",
                "series": [
                    {"key": "value", "name": "Ứng viên" if locale == "vi" else "Candidates"}
                ],
                "data": data,
            },
        },
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


async def _time_to_fill(session: AsyncSession, *, org_id: _uuid.UUID, locale: str) -> dict:
    from app.modules.recruitment.application import dashboard_read as rr

    samples = await rr.time_to_hire_samples(session, org_id=org_id)
    title = "Thời gian tuyển dụng" if locale == "vi" else "Time to fill"
    if not samples:
        return {"ok": True, "metric": "time_to_fill", "empty": True, "title": title}

    median_days = round(_median(samples), 1)
    avg_days = round(sum(samples) / len(samples), 1)

    # Per-stage average dwell time (visual breakdown of where time is spent).
    in_stage = await rr.time_in_stage_samples(session, org_id=org_id)
    data = [
        {
            "label": _label(_STAGE_TYPE_LABELS, stage_type, locale),
            "value": round(sum(vals) / len(vals), 1),
        }
        for stage_type, vals in in_stage.items()
        if vals
    ]

    result: dict = {
        "ok": True,
        "metric": "time_to_fill",
        "title": title,
        "median_days": median_days,
        "avg_days": avg_days,
        "sample_count": len(samples),
    }
    if data:
        result["render"] = {
            "kind": "chart",
            "chart": {
                "type": "bar",
                "title": (
                    "Thời gian trung bình mỗi vòng (ngày)"
                    if locale == "vi"
                    else "Average days per stage"
                ),
                "x_key": "label",
                "series": [{"key": "value", "name": "Ngày" if locale == "vi" else "Days"}],
                "data": data,
            },
        }
    return result


async def _source_mix(session: AsyncSession, *, org_id: _uuid.UUID, locale: str) -> dict:
    from app.modules.analytics.application import partner_job_metrics_service as pm

    title = "Nguồn ứng viên" if locale == "vi" else "Applicant source mix"
    perf = await pm.job_performance_for_org(session, org_id=org_id, since_days=90, limit=10_000)
    if not perf:
        return {"ok": True, "metric": "source_mix", "empty": True, "title": title}

    agg: dict[str, int] = dict.fromkeys(_SOURCE_LABELS, 0)
    for row in perf:
        mix = row.get("source_mix") or {}
        for k in agg:
            agg[k] += int(mix.get(k, 0) or 0)

    total = sum(agg.values())
    if total <= 0:
        return {"ok": True, "metric": "source_mix", "empty": True, "title": title}

    data = [
        {"label": _label(_SOURCE_LABELS, k, locale), "value": v}
        for k, v in agg.items()
        if v > 0
    ]
    return {
        "ok": True,
        "metric": "source_mix",
        "title": title,
        "total": total,
        "by_source": agg,
        "render": {
            "kind": "chart",
            "chart": {
                "type": "bar",
                "title": title,
                "x_key": "label",
                "series": [{"key": "value", "name": "Lượt" if locale == "vi" else "Visits"}],
                "data": data,
            },
        },
    }

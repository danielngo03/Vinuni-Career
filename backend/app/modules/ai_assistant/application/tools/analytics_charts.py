"""Partner analytics chart tools.

A single read-only tool, :func:`get_recruitment_analytics_chart`, turns the
recruitment read models (``dashboard_read``) into a chart the frontend renders
with Recharts. It follows the same FE-only ``render`` artifact contract as the
xlsx export tool: the handler returns a compact textual summary for the model
plus a ``render`` block that ``native_loop`` strips out of the model context and
attaches to the final assistant message. No candidate PII — aggregate counts
only, org-scoped to ``principal.org_id`` (the underlying read models filter by
org and soft-delete). No provider/model/token internals ever appear here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.permissions import Principal

# Localized labels for the coarse pipeline statuses used by the funnel chart.
# Enum codes never reach the user (see .claude/rules/ai.md) — these map to
# human labels in the caller's locale.
_STATUS_LABELS: dict[str, dict[str, str]] = {
    "submitted": {"vi": "Đã nộp", "en": "Submitted"},
    "under_review": {"vi": "Đang xem xét", "en": "Under review"},
    "shortlisted": {"vi": "Danh sách rút gọn", "en": "Shortlisted"},
    "interview": {"vi": "Phỏng vấn", "en": "Interview"},
    "offer": {"vi": "Đề nghị", "en": "Offer"},
    "hired": {"vi": "Đã tuyển", "en": "Hired"},
    "rejected": {"vi": "Từ chối", "en": "Rejected"},
    "withdrawn": {"vi": "Đã rút", "en": "Withdrawn"},
}

_CHART_TITLES: dict[str, dict[str, str]] = {
    "funnel": {"vi": "Phễu ứng tuyển", "en": "Application funnel"},
    "monthly_trend": {"vi": "Đơn ứng tuyển theo tháng", "en": "Applications by month"},
    "top_jobs": {"vi": "Tin tuyển dụng nhiều ứng viên nhất", "en": "Top jobs by applicants"},
    "pipeline_by_job": {"vi": "Pipeline theo từng tin", "en": "Pipeline by job"},
}

_VALID_CHARTS = frozenset(_CHART_TITLES)


def _loc(locale: str) -> str:
    return "en" if str(locale).lower().startswith("en") else "vi"


def _status_label(status: str, locale: str) -> str:
    entry = _STATUS_LABELS.get(status)
    return entry[locale] if entry else status.replace("_", " ").title()


async def get_recruitment_analytics_chart(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Build one recruitment analytics chart from real aggregate data.

    ``chart`` ∈ {funnel, monthly_trend, top_jobs, pipeline_by_job}. Returns a
    small summary for the model plus a ``render`` chart artifact for the FE.
    """
    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    chart = (args.get("chart") or "funnel").strip().lower()
    if chart not in _VALID_CHARTS:
        return {"ok": False, "error": "unknown_chart", "valid": sorted(_VALID_CHARTS)}
    locale = _loc(args.get("locale") or "vi")
    org_id = principal.org_id
    title = _CHART_TITLES[chart][locale]
    applicants_name = "Ứng viên" if locale == "vi" else "Applicants"

    from app.modules.recruitment.application import dashboard_read as rr

    try:
        if chart == "funnel":
            rows = await rr.analytics_application_funnel(session, org_id=org_id)
            data = [
                {"label": _status_label(r["status"], locale), "value": r["count"]} for r in rows
            ]
            spec = {
                "type": "bar",
                "title": title,
                "x_key": "label",
                "series": [{"key": "value", "name": applicants_name}],
                "data": data,
            }
        elif chart == "monthly_trend":
            rows = await rr.analytics_monthly_trend(session, org_id=org_id, months=6)
            data = [{"label": r["month"], "value": r["count"]} for r in rows]
            spec = {
                "type": "line",
                "title": title,
                "x_key": "label",
                "series": [{"key": "value", "name": applicants_name}],
                "data": data,
            }
        elif chart == "top_jobs":
            rows = await rr.analytics_top_jobs(session, org_id=org_id, limit=6)
            data = [{"label": r["title"], "value": r["application_count"]} for r in rows]
            spec = {
                "type": "bar",
                "title": title,
                "x_key": "label",
                "series": [{"key": "value", "name": applicants_name}],
                "data": data,
            }
        else:  # pipeline_by_job
            rows = await rr.pipeline_overview_for_org(session, org_id=org_id, limit=8)
            active_name = "Đang hoạt động" if locale == "vi" else "Active"
            rejected_name = "Từ chối" if locale == "vi" else "Rejected"
            data = [
                {
                    "label": r.get("title", "—"),
                    "active": r.get("active_total", 0),
                    "rejected": r.get("rejected", 0),
                }
                for r in rows
            ]
            spec = {
                "type": "bar",
                "title": title,
                "x_key": "label",
                "series": [
                    {"key": "active", "name": active_name},
                    {"key": "rejected", "name": rejected_name},
                ],
                "data": data,
            }
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    if not spec["data"]:
        # Honest empty state — no fabricated data (.claude/rules/frontend.md).
        return {"ok": True, "chart": chart, "empty": True, "title": title}

    # Compact summary for the model's context (the full data goes only to the FE
    # via ``render``, which native_loop strips before the model sees the result).
    data_rows: list[dict[str, Any]] = [row for row in spec.get("data", []) if isinstance(row, dict)]
    total = sum(
        row.get("value") or row.get("active", 0) + row.get("rejected", 0) for row in data_rows
    )
    return {
        "ok": True,
        "chart": chart,
        "title": title,
        "point_count": len(data_rows),
        "total": total,
        "render": {"kind": "chart", "chart": spec},
    }


# Ordered active-pipeline progression for the funnel-flow diagram.
_FUNNEL_ORDER = ["submitted", "under_review", "shortlisted", "interview", "offer", "hired"]


async def get_hiring_funnel_diagram(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Render the org's hiring funnel as a stage-flow diagram with drop-off.

    Unlike the bar chart, this shows the PROGRESSION between pipeline stages and
    the conversion (% of applicants who reached each stage vs the first) — the
    recruiter's drop-off view. Aggregate counts only, org-scoped.
    """
    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}
    locale = _loc(args.get("locale") or "vi")
    title = "Phễu tuyển dụng" if locale == "vi" else "Hiring funnel"

    from app.modules.recruitment.application import dashboard_read as rr

    try:
        rows = await rr.analytics_application_funnel(session, org_id=principal.org_id)
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    by_status = {r["status"]: r["count"] for r in rows}
    # Progression stages up to the deepest one that has candidates (trim trailing 0s).
    ordered = [(s, by_status.get(s, 0)) for s in _FUNNEL_ORDER]
    while ordered and ordered[-1][1] == 0:
        ordered.pop()
    if not ordered or ordered[0][1] == 0:
        return {"ok": True, "empty": True, "title": title}

    top = ordered[0][1]
    stages = [
        {
            "label": _status_label(s, locale),
            "count": c,
            # % of the first stage that reached this stage (drop-off view).
            "pct": round(100 * c / top) if top else 0,
        }
        for s, c in ordered
    ]
    return {
        "ok": True,
        "title": title,
        "stage_count": len(stages),
        "top_stage_count": top,
        "render": {
            "kind": "diagram",
            "diagram": {"type": "funnel", "title": title, "stages": stages},
        },
    }

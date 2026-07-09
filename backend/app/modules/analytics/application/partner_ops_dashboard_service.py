"""Partner Dashboard V2 (spec §"Partner Dashboard V2 Contract"): ``GET
/dashboards/partner/ops``.

Additive to (never replacing) the existing ``GET /dashboards/partner`` v1
surface (`app.modules.dashboards.application.partner_dashboard`) — v1 stays the
lightweight glance card; this is the fuller command-center read model with
job-performance/team-activity/access-alert/RBAC widgets.

Every widget degrades independently and never fabricates data: a widget the
viewer lacks the grant for reports ``locked: true`` + a reason instead of a fake
zero; a widget backed by a projection that has no rows yet reports
``basis: "application_counts_only"`` (or similar) instead of a silent zero.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.application import (
    partner_activity_feed_service,
    partner_candidate_access_service,
    partner_job_metrics_service,
    rbac_capability_service,
)
from app.modules.auth.domain import personas
from app.modules.dashboards.application._common import RECENT_CAP, empty_rows, safe
from app.modules.messaging.application import message_service
from app.modules.opportunities.application import dashboard_read as opportunities_read
from app.modules.opportunities.application import job_read_facade
from app.modules.organization.application import org_reporting_facade
from app.modules.recruitment.application import dashboard_read as recruitment_read
from app.modules.recruitment.domain import offer as offer_domain
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError, ResourceNotFoundError
from app.shared.permissions import Principal


def _require_partner(principal: Principal) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.persona != personas.PARTNER_MEMBER:
        raise PermissionDeniedError()


async def _todos(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    job_counts: dict,
    reveals_pending: int,
    access_alerts: list[dict],
    apps_to_review: int = 0,
    offers_to_approve: int = 0,
    offers_to_send: int = 0,
    unread_messages: int = 0,
) -> list[dict]:
    """Partner-ACTIONABLE work queue.

    Every item is something the partner can act on right now; ``count`` is the size
    of the backlog and ``kind`` distinguishes an actionable todo from an
    ``informational`` awareness item. Ordered high → low so the UI can render the
    most urgent first.
    """

    todos: list[dict] = []
    if apps_to_review > 0:
        todos.append(
            {
                "key": "applications_to_review",
                "href": "/partner/candidates",
                "count": apps_to_review,
                "priority": "high",
                "kind": "action",
            }
        )
    if offers_to_approve > 0:
        todos.append(
            {
                "key": "offers_to_approve",
                "href": "/partner/candidates",
                "count": offers_to_approve,
                "priority": "high",
                "kind": "action",
            }
        )
    if offers_to_send > 0:
        todos.append(
            {
                "key": "offers_to_send",
                "href": "/partner/candidates",
                "count": offers_to_send,
                "priority": "medium",
                "kind": "action",
            }
        )
    if access_alerts:
        todos.append(
            {
                "key": "review_access_alerts",
                "href": "/partner/security",
                "count": len(access_alerts),
                "priority": "high",
                "kind": "action",
            }
        )
    if job_counts["pending_review"] > 0:
        todos.append(
            {
                "key": "jobs_pending_review",
                "href": "/partner/jobs",
                "count": job_counts["pending_review"],
                "priority": "medium",
                "kind": "action",
            }
        )
    if job_counts["draft"] > 0:
        todos.append(
            {
                "key": "jobs_in_draft",
                "href": "/partner/jobs",
                "count": job_counts["draft"],
                "priority": "medium",
                "kind": "action",
            }
        )
    if unread_messages > 0:
        todos.append(
            {
                "key": "unread_messages",
                "href": "/partner/messages",
                "count": unread_messages,
                "priority": "medium",
                "kind": "action",
            }
        )
    # Reveal requests are answered by the STUDENT, not the partner — so this is an
    # awareness item (outreach in flight), never framed as a partner action. This
    # replaces the old, misleading ``respond_reveals`` action todo.
    if reveals_pending > 0:
        todos.append(
            {
                "key": "reveals_awaiting_candidate",
                "href": "/partner/candidates",
                "count": reveals_pending,
                "priority": "low",
                "kind": "informational",
            }
        )
    todos.append(
        {
            "key": "post_job",
            "href": "/partner/jobs/new",
            "count": None,
            "priority": "low",
            "kind": "action",
        }
    )
    return todos


async def get_partner_dashboard_ops(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    _require_partner(principal)
    org_id = principal.org_id
    if org_id is None:
        raise ResourceNotFoundError()

    org_name = await safe(
        session, lambda: org_reporting_facade.display_name_for(session, org_id), fallback=None
    )

    # --- base counts (same real read models as dashboard v1) ---------------- #
    job_counts = await safe(
        session,
        lambda: opportunities_read.count_org_jobs_by_status(session, org_id=org_id),
        fallback={"active": 0, "draft": 0, "pending_review": 0, "rejected": 0, "closed": 0},
    )
    applications_total = await safe(
        session,
        lambda: recruitment_read.count_org_applications(session, org_id=org_id),
        fallback=0,
    )
    reveals_pending = await safe(
        session,
        lambda: recruitment_read.count_org_pending_reveals(session, org_id=org_id),
        fallback=0,
    )

    # --- rbac_summary (always computable; drives the other widgets' gates) -- #
    rbac_summary = rbac_capability_service.capability_summary(principal, org_id=org_id)
    can_view_metrics = rbac_summary["grants"]["analytics:view_job_metrics"]
    can_view_access_log = (
        rbac_summary["grants"]["candidate_identity:download_cv"] or rbac_summary["is_org_admin"]
    )

    # --- metrics: real counts + conversion metrics when the projection exists #
    metrics: dict = {
        "jobs_active": job_counts["active"],
        "jobs_draft": job_counts["draft"],
        "jobs_pending_review": job_counts["pending_review"],
        "applications_total": applications_total,
        "reveals_pending_response": reveals_pending,
    }
    if can_view_metrics:
        org_summary = await safe(
            session,
            lambda: partner_job_metrics_service.org_metrics_summary(session, org_id=org_id),
            fallback=None,
        )
        if org_summary is None:
            metrics["engagement"] = {
                "available": False,
                "basis": "application_counts_only",
                "reason": "no_metrics_yet",
            }
        else:
            metrics["engagement"] = {"available": True, "basis": "job_metrics_daily", **org_summary}
    else:
        metrics["engagement"] = {"available": False, "basis": "locked", "reason": "missing_grant"}

    # --- job_performance: top/at-risk jobs, gated on analytics:view_job_metrics
    if can_view_metrics:
        performance_rows: list[dict] = await safe(
            session,
            lambda: partner_job_metrics_service.job_performance_for_org(
                session, org_id=org_id, limit=10
            ),
            fallback=empty_rows(),
        )
        if performance_rows:
            titles = await job_read_facade.get_job_titles(
                session, (uuid.UUID(r["job_id"]) for r in performance_rows)
            )
            for r in performance_rows:
                r["title"] = titles.get(uuid.UUID(r["job_id"])) or "—"
            job_performance = {
                "locked": False,
                "basis": "job_metrics_daily",
                "items": performance_rows,
            }
        else:
            # Honest fallback: no click/view projection rows yet -> fall back to
            # the application-count-only top-jobs widget that already exists.
            top_jobs: list[dict] = await safe(
                session,
                lambda: recruitment_read.analytics_top_jobs(session, org_id=org_id, limit=10),
                fallback=empty_rows(),
            )
            job_performance = {
                "locked": False,
                "basis": "application_counts_only",
                "items": top_jobs,
            }
    else:
        job_performance = {"locked": True, "reason": "missing_grant", "items": []}

    # --- team_activity: derived from audit_logs, filtered by grants/dept ----- #
    team_activity = await safe(
        session,
        lambda: partner_activity_feed_service.list_partner_activity_feed(
            session, principal=principal, org_id=org_id, limit=RECENT_CAP, locale=locale
        ),
        fallback=empty_rows(),
    )

    # --- access_alerts: CV-download / reveal-request spikes ------------------ #
    if can_view_access_log:
        access_alerts = await safe(
            session,
            lambda: partner_candidate_access_service.detect_access_alerts(
                session, org_id=org_id, locale=locale
            ),
            fallback=empty_rows(),
        )
        access_alerts_widget = {"locked": False, "items": access_alerts}
    else:
        access_alerts = []
        access_alerts_widget = {"locked": True, "reason": "missing_grant", "items": []}

    # --- actionable work counts for the ops queue (all cheap indexed counts) - #
    apps_to_review = await safe(
        session,
        lambda: recruitment_read.count_org_applications_needing_review(session, org_id=org_id),
        fallback=0,
    )
    offers_to_approve = await safe(
        session,
        lambda: recruitment_read.count_org_offers_by_status(
            session, org_id=org_id, statuses=(offer_domain.STATUS_PENDING_APPROVAL,)
        ),
        fallback=0,
    )
    offers_to_send = await safe(
        session,
        lambda: recruitment_read.count_org_offers_by_status(
            session, org_id=org_id, statuses=(offer_domain.STATUS_APPROVED,)
        ),
        fallback=0,
    )
    unread_messages = await safe(
        session,
        lambda: message_service.unread_count(session, principal=principal),
        fallback=0,
    )

    todos = await _todos(
        session,
        org_id=org_id,
        job_counts=job_counts,
        reveals_pending=reveals_pending,
        access_alerts=access_alerts,
        apps_to_review=apps_to_review,
        offers_to_approve=offers_to_approve,
        offers_to_send=offers_to_send,
        unread_messages=unread_messages,
    )

    # --- ai_recommendations: advisory-only, rule-based heuristics ------------ #
    # NOTE: deterministic backend heuristics, NOT a live AI/LLM call — this is a
    # documented simplification pending `ai-engineer` wiring a real advisory tool
    # into this widget. Never claims to be AI-graded; always advisory + labeled.
    ai_recommendations: list[dict] = []
    if job_counts["draft"] > 0:
        ai_recommendations.append(
            {
                "code": "publish_drafts",
                "message_vi": (
                    "Bạn có tin tuyển dụng ở dạng nháp — hãy hoàn tất và gửi "
                    "duyệt để bắt đầu nhận hồ sơ."
                ),
                "message_en": (
                    "You have draft jobs — finish and submit them for review "
                    "to start receiving applications."
                ),
                "advisory_only": True,
            }
        )
    if reveals_pending > 0:
        ai_recommendations.append(
            {
                "code": "respond_reveals_pending",
                "message_vi": "Có yêu cầu tiết lộ danh tính đang chờ ứng viên phản hồi.",
                "message_en": "You have identity-reveal requests awaiting candidate response.",
                "advisory_only": True,
            }
        )
    if (
        can_view_metrics
        and metrics["engagement"].get("available")
        and metrics["engagement"].get("conversion_rate_pct") is not None
    ):
        conv = metrics["engagement"]["conversion_rate_pct"]
        if conv < 2:
            ai_recommendations.append(
                {
                    "code": "low_conversion",
                    "message_vi": (
                        "Tỷ lệ chuyển đổi từ lượt xem sang hồ sơ ứng tuyển đang "
                        "thấp — cân nhắc xem lại mô tả công việc."
                    ),
                    "message_en": (
                        "View-to-application conversion is low — consider "
                        "reviewing the job description."
                    ),
                    "advisory_only": True,
                }
            )

    return {
        "org_name": org_name,
        "todos": todos,
        "metrics": metrics,
        "job_performance": job_performance,
        "team_activity": team_activity,
        "access_alerts": access_alerts_widget,
        "rbac_summary": rbac_summary,
        "ai_recommendations": ai_recommendations,
    }

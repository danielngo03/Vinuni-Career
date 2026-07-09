"""Unified university operations command-center read model (``GET /dashboards/university/ops``).

Aggregates every university operational queue into function groups, each with an
open + overdue roll-up, so the university dashboard can show "what needs doing"
grouped by function (moderation, partner & support, trust & safety, career
services) with one deep-link per queue.

Boundary discipline: this read model never touches another module's ORM. Each
source module exposes a thin ``ops_queue_read.queue_counts(session, *, kind, now)``
application facade (which may legally query its OWN ORM), and this service only
imports those facades — exactly like :mod:`university_dashboard` imports
``opportunities_read`` / ``partner_registration_service``.

RBAC mirrors the university command-center gate
(:func:`university_dashboard._require_university`): platform superadmin, or a
member of a **university** org holding ``jobs:moderate``. Wrong persona -> 403.

Failure tolerance: every per-queue count runs inside :func:`_common.safe`, so one
failing queue degrades to ``0`` open / ``0`` overdue and the envelope is always
well-formed — a single failing queue never 500s the page. Overdue/SLA windows
come from the one shared policy table in :mod:`app.shared.moderation`.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.advertising.application import ops_queue_read as advertising_ops
from app.modules.career_services.application import ops_queue_read as career_services_ops
from app.modules.compliance.application import ops_queue_read as compliance_ops
from app.modules.dashboards.application import university_dashboard
from app.modules.dashboards.application._common import safe
from app.modules.moderation.application import ops_queue_read as moderation_ops
from app.modules.opportunities.application import ops_queue_read as opportunities_ops
from app.modules.organization.application import ops_queue_read as organization_ops
from app.modules.platform_support.application import ops_queue_read as platform_support_ops
from app.modules.reviews.application import ops_queue_read as reviews_ops
from app.shared import moderation as sla
from app.shared.permissions import Principal

_FALLBACK: dict[str, int] = {"open": 0, "overdue": 0}

# Group order is stable (highest-frequency operational surfaces first).
_GROUP_ORDER = ("moderation", "partner_support", "trust_safety", "career_services")

_GROUP_LABELS: dict[str, dict[str, str]] = {
    "moderation": {"vi": "Kiểm duyệt nội dung", "en": "Content moderation"},
    "partner_support": {"vi": "Đối tác & hỗ trợ", "en": "Partners & support"},
    "trust_safety": {"vi": "An toàn & tuân thủ", "en": "Trust & safety"},
    "career_services": {"vi": "Dịch vụ hướng nghiệp", "en": "Career services"},
}

# Queue key == SLA kind. Localized so the client never renders a bare enum code.
_QUEUE_LABELS: dict[str, dict[str, str]] = {
    sla.QUEUE_JOB_POSTING: {"vi": "Tin tuyển dụng chờ duyệt", "en": "Jobs pending review"},
    sla.QUEUE_EVENT: {"vi": "Sự kiện chờ duyệt", "en": "Events pending review"},
    sla.QUEUE_AD_CREATIVE: {
        "vi": "Quảng cáo tài trợ chờ duyệt",
        "en": "Sponsored ads pending review",
    },
    sla.QUEUE_PARTNER_REGISTRATION: {
        "vi": "Đăng ký đối tác chờ duyệt",
        "en": "Partner registrations",
    },
    sla.QUEUE_SUPPORT_CASE: {"vi": "Yêu cầu hỗ trợ đang mở", "en": "Open support cases"},
    sla.QUEUE_CONTENT_REPORT: {"vi": "Báo cáo nội dung", "en": "Content reports"},
    sla.QUEUE_AI_FLAGGED: {"vi": "Cảnh báo AI chờ xử lý", "en": "AI-flagged review"},
    sla.QUEUE_PRIVACY_REQUEST: {"vi": "Yêu cầu quyền riêng tư", "en": "Privacy requests"},
    sla.QUEUE_COMPANY_REVIEW: {
        "vi": "Đánh giá công ty bị báo cáo",
        "en": "Reported company reviews",
    },
    sla.QUEUE_CV_REVIEW: {"vi": "CV chờ phản hồi", "en": "CV reviews"},
    sla.QUEUE_AT_RISK: {"vi": "Sinh viên cần hỗ trợ", "en": "At-risk students"},
}

# A per-queue count function: ``queue_counts(session, *, kind, now)`` returning
# ``{"open": int, "overdue": int}`` for that one queue kind.
_QueueCounts = Callable[..., Awaitable[dict[str, int]]]

# (group_key, kind, count function, deep-link href).
_QUEUES: tuple[tuple[str, str, _QueueCounts, str], ...] = (
    (
        "moderation",
        sla.QUEUE_JOB_POSTING,
        opportunities_ops.queue_counts,
        "/university/moderation/jobs",
    ),
    (
        "moderation",
        sla.QUEUE_EVENT,
        opportunities_ops.queue_counts,
        "/university/moderation/events",
    ),
    ("moderation", sla.QUEUE_AD_CREATIVE, advertising_ops.queue_counts, "/university/advertising"),
    (
        "partner_support",
        sla.QUEUE_PARTNER_REGISTRATION,
        organization_ops.queue_counts,
        "/university/partners",
    ),
    (
        "partner_support",
        sla.QUEUE_SUPPORT_CASE,
        platform_support_ops.queue_counts,
        "/university/support",
    ),
    ("trust_safety", sla.QUEUE_CONTENT_REPORT, moderation_ops.queue_counts, "/university/abuse"),
    ("trust_safety", sla.QUEUE_AI_FLAGGED, moderation_ops.queue_counts, "/university/abuse"),
    ("trust_safety", sla.QUEUE_PRIVACY_REQUEST, compliance_ops.queue_counts, "/university/privacy"),
    ("trust_safety", sla.QUEUE_COMPANY_REVIEW, reviews_ops.queue_counts, "/university/reviews"),
    (
        "career_services",
        sla.QUEUE_CV_REVIEW,
        career_services_ops.queue_counts,
        "/university/career-services/cv-review",
    ),
    (
        "career_services",
        sla.QUEUE_AT_RISK,
        career_services_ops.queue_counts,
        "/university/career-services/at-risk",
    ),
)


def _loc(labels: dict[str, str], locale: str) -> str:
    return labels.get(locale, labels["vi"])


async def get_university_ops(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    """Assemble the grouped ops command-center read model (university-gated)."""

    await university_dashboard._require_university(session, principal)

    now = datetime.now(tz=UTC)
    groups: dict[str, dict] = {}

    for group_key, kind, counts_fn, href in _QUEUES:
        counts = await safe(
            session,
            # partial binds each queue's args eagerly (no late-binding closure bug).
            functools.partial(counts_fn, session, kind=kind, now=now),
            fallback=dict(_FALLBACK),
        )
        open_ = int(counts.get("open", 0))
        overdue = int(counts.get("overdue", 0))

        group = groups.setdefault(
            group_key,
            {
                "key": group_key,
                "label": _loc(_GROUP_LABELS[group_key], locale),
                "open_total": 0,
                "overdue_total": 0,
                "queues": [],
            },
        )
        group["queues"].append(
            {
                "key": kind,
                "kind": kind,
                "label": _loc(_QUEUE_LABELS[kind], locale),
                "href": href,
                "open": open_,
                "overdue": overdue,
                "sla_hours": sla.sla_hours_for(kind),
            }
        )
        group["open_total"] += open_
        group["overdue_total"] += overdue

    ordered = [groups[key] for key in _GROUP_ORDER if key in groups]
    totals = {
        "open": sum(g["open_total"] for g in ordered),
        "overdue": sum(g["overdue_total"] for g in ordered),
    }
    return {"groups": ordered, "totals": totals}

"""Abuse/fraud triage: merged list, escalate, override (ADR-0014, §35).

The triage list *merges* ``content_reports`` with ``human_review_queue`` as a
read-only aggregation query (not a new projection table at V1 volume —
revisit as a projection if it becomes a dashboard hot path, per the ADR).

Severity at escalation time is heuristic (ADR-0014 "Risk Flagged To
Product"): a single report -> ``low``; N reports on the same entity within a
window -> ``medium``; corroborates an existing pending ``fraud_detection``
item on the same ``resource_id`` -> ``high``. This mirrors how
``fraud_scan_service`` already assigns a fixed severity at its own
escalation call site (no separate confidence field is introduced).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.moderation.domain.models import (
    REPORT_STATUS_PENDING,
    REPORT_STATUS_TRIAGED,
    SOURCE_FRAUD,
    SOURCE_USER_REPORT,
    STATUS_PENDING,
    ContentReport,
    HumanReviewItem,
)
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.pagination import clamp_limit
from app.shared.permissions import Principal, permission_checker

_CORROBORATION_WINDOW = timedelta(days=14)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def _require_abuse(
    session: AsyncSession, principal: Principal, action: str
) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.is_superadmin:
        return
    if not permission_checker.can(principal, "abuse", action):
        raise PermissionDeniedError()
    if not await org_reporting_facade.is_university_org(session, principal.org_id):
        raise PermissionDeniedError(details={"reason": "university_only"})


def _present_report(row: ContentReport) -> dict:
    return {
        "kind": "content_report",
        "id": str(row.id),
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id),
        "reason_code": row.reason_code,
        "status": row.status,
        "review_item_id": str(row.review_item_id) if row.review_item_id else None,
        "created_at": row.created_at.isoformat(),
    }


def _present_review_item(item: HumanReviewItem) -> dict:
    return {
        "kind": "human_review_item",
        "id": str(item.id),
        "source": item.source,
        "resource_type": item.resource_type,
        "resource_id": str(item.resource_id) if item.resource_id else None,
        "severity": item.severity,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
    }


async def list_triage(
    session: AsyncSession,
    *,
    principal: Principal,
    source: str | None = None,
    limit: int = 50,
) -> list[dict]:
    await _require_abuse(session, principal, "read")
    limit = clamp_limit(limit)

    items: list[dict] = []
    if source is None or source == SOURCE_USER_REPORT:
        report_stmt = (
            select(ContentReport)
            .where(
                ContentReport.status.in_(
                    (REPORT_STATUS_PENDING, REPORT_STATUS_TRIAGED)
                )
            )
            .order_by(ContentReport.created_at.desc())
            .limit(limit)
        )
        reports = (await session.execute(report_stmt)).scalars().all()
        items.extend(_present_report(r) for r in reports)

    review_stmt = select(HumanReviewItem).order_by(HumanReviewItem.created_at.desc())
    if source is not None:
        if source == SOURCE_USER_REPORT:
            review_stmt = review_stmt.where(HumanReviewItem.source == SOURCE_USER_REPORT)
        else:
            review_stmt = review_stmt.where(HumanReviewItem.source == source)
    review_stmt = review_stmt.limit(limit)
    review_rows = (await session.execute(review_stmt)).scalars().all()
    items.extend(_present_review_item(r) for r in review_rows)

    # Default sort/priority (ADR-0014 risk note): never treat a single
    # unverified user report as equally urgent as a fraud-detector hit.
    severity_rank = {"high": 0, "medium": 1, "low": 2}

    def _sort_key(entry: dict) -> tuple[int, str]:
        severity = entry.get("severity", "low")
        return (severity_rank.get(severity, 2), entry.get("created_at", ""))

    items.sort(key=_sort_key)
    return items[:limit]


async def _severity_for_escalation(
    session: AsyncSession, *, report: ContentReport
) -> str:
    same_entity_count = (
        await session.execute(
            select(func.count())
            .select_from(ContentReport)
            .where(
                ContentReport.entity_type == report.entity_type,
                ContentReport.entity_id == report.entity_id,
                ContentReport.created_at >= _now() - _CORROBORATION_WINDOW,
            )
        )
    ).scalar_one()

    corroborates_fraud = (
        await session.execute(
            select(HumanReviewItem.id).where(
                HumanReviewItem.source == SOURCE_FRAUD,
                HumanReviewItem.resource_id == report.entity_id,
                HumanReviewItem.status == STATUS_PENDING,
            )
        )
    ).first()
    if corroborates_fraud is not None:
        return "high"
    if same_entity_count and same_entity_count > 1:
        return "medium"
    return "low"


async def escalate_report(
    session: AsyncSession,
    *,
    principal: Principal,
    report_id: uuid.UUID,
    ctx: RequestContext,
) -> dict:
    await _require_abuse(session, principal, "triage")

    report = (
        await session.execute(select(ContentReport).where(ContentReport.id == report_id))
    ).scalar_one_or_none()
    if report is None:
        raise ResourceNotFoundError()

    severity = await _severity_for_escalation(session, report=report)

    review_item = (
        await session.execute(
            select(HumanReviewItem).where(
                HumanReviewItem.source == SOURCE_USER_REPORT,
                HumanReviewItem.resource_type == report.entity_type,
                HumanReviewItem.resource_id == report.entity_id,
                HumanReviewItem.status == STATUS_PENDING,
            )
        )
    ).scalar_one_or_none()

    findings = {
        "reason_code": report.reason_code,
        "note": report.note,
        "report_count": 1,
    }
    if review_item is not None:
        review_item.findings_json = findings
        review_item.severity = severity
        review_item.updated_at = _now()
    else:
        review_item = HumanReviewItem(
            source=SOURCE_USER_REPORT,
            resource_type=report.entity_type,
            resource_id=report.entity_id,
            org_id=report.reporter_org_id,
            severity=severity,
            status=STATUS_PENDING,
            findings_json=findings,
        )
        session.add(review_item)
    await session.flush()

    before = {"status": report.status}
    report.review_item_id = review_item.id
    report.status = REPORT_STATUS_TRIAGED
    await session.flush()

    await write_audit(
        session,
        action="abuse.report_escalated",
        resource_type="content_report",
        resource_id=report.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after={
            "status": report.status,
            "severity": severity,
            "review_item_id": str(review_item.id),
        },
    )
    await session.commit()
    return _present_report(report)


# --------------------------------------------------------------------------- #
# Override — the one write path that must carry a real before/after diff     #
# --------------------------------------------------------------------------- #

# Resource-type reversal handlers, kept intentionally small (V1 scope): each
# returns (before_state, after_state) or ``None`` if no wired reversal exists
# for that resource type (documented gap — the override is still audited on
# the review item, just without a resource-side effect).
async def _reverse_user_suspension(
    session: AsyncSession, *, resource_id: uuid.UUID, principal: Principal
) -> tuple[dict, dict] | None:
    from app.modules.users.application import admin_users_service

    # The abuse-override authority is ``abuse:override`` (already checked in
    # ``override_action``) — not ``accounts:govern`` — and this path owns its own
    # audit + commit, so it uses the raw flip helper rather than the audited/
    # committing ``unsuspend_user`` governance entrypoint.
    result = await admin_users_service.set_user_active(
        session, user_id=resource_id, active=True, actor_user_id=principal.user_id
    )
    return {"is_active": False}, {"is_active": result["is_active"]}


async def override_action(
    session: AsyncSession,
    *,
    principal: Principal,
    review_item_id: uuid.UUID,
    note: str,
    ctx: RequestContext,
) -> dict:
    await _require_abuse(session, principal, "override")
    if not note or not note.strip():
        raise ValidationFailedError(details={"field": "note"})

    item = (
        await session.execute(
            select(HumanReviewItem).where(HumanReviewItem.id == review_item_id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise ResourceNotFoundError()

    # V1 scope: only ``resource_type == "user"`` has a wired reversal facade
    # (``admin_users_service.unsuspend_user``). Other resource types
    # (job/event/placement republish, content unflag) have no dedicated
    # override facade yet — documented gap, flagged to `system-architect`
    # rather than silently faked; the override is still fully audited on the
    # review item itself.
    before: dict = {"status": item.status}
    after: dict = {"status": item.status}
    if item.resource_id is not None and item.resource_type == "user":
        diff = await _reverse_user_suspension(
            session, resource_id=item.resource_id, principal=principal
        )
        if diff is not None:
            before, after = diff

    item.resolution_note = note.strip()[:2000]
    item.reviewed_by = principal.user_id
    item.reviewed_at = _now()
    item.updated_at = _now()
    await session.flush()

    await write_audit(
        session,
        action="abuse.action_overridden",
        resource_type="support_abuse_override",
        resource_id=item.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after=after,
    )
    await session.commit()
    return _present_review_item(item)

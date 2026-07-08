"""``partner_activity_feed`` read service (spec §"Recruiting Intelligence Read
Models" -> ``partner_activity_feed``).

Per the spec this feed is DERIVED from the existing ``audit_logs`` writer
(``app.shared.audit``) rather than a second duplicated storage table — every
action listed here (job lifecycle, candidate decisions, scorecard/interview/
offer changes, role/member/department/billing changes) already calls
``write_audit`` from its owning service. This module is a read-only query +
capability filter over that existing ledger, scoped to one org and to the
viewing principal's own grants (a member without ``billing:view`` never sees a
billing row, even though the row exists in the shared ledger).

Department scoping (spec: "filtered by ... department scope"): the current data
model does not tag ``jobs``/``applications`` with an owning department, so a
literal per-resource department filter is not yet possible. As an honest
approximation, when the viewing principal's OWN membership is department-scoped
(has a department assignment) and lacks an org-wide members/roles capability,
the feed narrows to rows whose actor shares at least one department with the
viewer. This is documented as an interim approximation — a real per-resource
department tag is a `system-architect` follow-up once jobs/applications carry
an owning department.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.application import org_reporting_facade
from app.modules.users.application import user_service
from app.shared.models import AuditLog
from app.shared.permissions import Principal, permission_checker

# action prefix -> (required capability tuple, vi label, en label)
_ACTION_CAPABILITY: dict[str, tuple[str, str]] = {
    "job.": ("jobs", "read"),
    "application.": ("applications", "read"),
    "membership.": ("members", "read"),
    "invitation.": ("members", "read"),
    "role.": ("roles", "read"),
    "department.": ("departments", "read"),
    "organization.": ("organizations", "read"),
    "billing.": ("billing", "view"),
}

_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "job.created": "Đã tạo tin tuyển dụng",
        "job.updated": "Đã cập nhật tin tuyển dụng",
        "job.submit": "Đã gửi duyệt tin tuyển dụng",
        "job.deleted": "Đã xoá tin tuyển dụng",
        "job.duplicated": "Đã nhân bản tin tuyển dụng",
        "application.reviewed": "Đã xem xét hồ sơ ứng tuyển",
        "application.rejected": "Đã từ chối hồ sơ ứng tuyển",
        "application.stage_advanced": "Đã chuyển giai đoạn ứng viên",
        "application.stage_rolled_back": "Đã lùi giai đoạn ứng viên",
        "application.hired": "Đã tuyển ứng viên",
        "application.reveal_requested": "Đã gửi yêu cầu tiết lộ danh tính",
        "application.reveal_responded": "Ứng viên đã phản hồi yêu cầu tiết lộ",
        "application.offer_created": "Đã tạo đề nghị làm việc",
        "application.offer_submitted": "Đã gửi duyệt đề nghị làm việc",
        "application.offer_sent": "Đã gửi đề nghị làm việc cho ứng viên",
        "application.offer_rescinded": "Đã thu hồi đề nghị làm việc",
        "application.interview_scheduled": "Đã lên lịch phỏng vấn",
        "application.interview_rescheduled": "Đã dời lịch phỏng vấn",
        "application.interview_cancelled": "Đã huỷ lịch phỏng vấn",
        "membership.created": "Đã thêm thành viên",
        "membership.updated": "Đã cập nhật thành viên",
        "membership.removed": "Đã xoá thành viên",
        "invitation.created": "Đã mời thành viên mới",
        "invitation.revoked": "Đã thu hồi lời mời",
        "role.created": "Đã tạo vai trò",
        "role.updated": "Đã cập nhật vai trò",
        "role.deleted": "Đã xoá vai trò",
        "department.created": "Đã tạo phòng ban",
        "department.updated": "Đã cập nhật phòng ban",
        "department.deleted": "Đã xoá phòng ban",
        "organization.updated": "Đã cập nhật thông tin tổ chức",
        "billing.subscription_requested": "Đã yêu cầu gói dịch vụ",
        "billing.subscription_paid": "Đã xác nhận thanh toán gói dịch vụ",
    },
    "en": {
        "job.created": "Job created",
        "job.updated": "Job updated",
        "job.submit": "Job submitted for review",
        "job.deleted": "Job deleted",
        "job.duplicated": "Job duplicated",
        "application.reviewed": "Application reviewed",
        "application.rejected": "Application rejected",
        "application.stage_advanced": "Candidate moved forward",
        "application.stage_rolled_back": "Candidate moved back",
        "application.hired": "Candidate hired",
        "application.reveal_requested": "Identity reveal requested",
        "application.reveal_responded": "Candidate responded to reveal request",
        "application.offer_created": "Offer created",
        "application.offer_submitted": "Offer submitted for approval",
        "application.offer_sent": "Offer sent to candidate",
        "application.offer_rescinded": "Offer rescinded",
        "application.interview_scheduled": "Interview scheduled",
        "application.interview_rescheduled": "Interview rescheduled",
        "application.interview_cancelled": "Interview cancelled",
        "membership.created": "Team member added",
        "membership.updated": "Team member updated",
        "membership.removed": "Team member removed",
        "invitation.created": "Invitation sent",
        "invitation.revoked": "Invitation revoked",
        "role.created": "Role created",
        "role.updated": "Role updated",
        "role.deleted": "Role deleted",
        "department.created": "Department created",
        "department.updated": "Department updated",
        "department.deleted": "Department deleted",
        "organization.updated": "Organization profile updated",
        "billing.subscription_requested": "Plan subscription requested",
        "billing.subscription_paid": "Plan payment confirmed",
    },
}


def _capability_for(action: str) -> tuple[str, str] | None:
    for prefix, cap in _ACTION_CAPABILITY.items():
        if action.startswith(prefix):
            return cap
    return None


def _label(action: str, *, locale: str) -> str:
    return _LABELS.get(locale, _LABELS["vi"]).get(action, action)


async def _viewer_department_ids(
    session: AsyncSession, *, principal: Principal
) -> set[uuid.UUID] | None:
    """The viewer's own department ids, or ``None`` if not department-scoped."""

    if principal.user_id is None or principal.org_id is None:
        return None
    dept_ids = await org_reporting_facade.department_ids_for_user_in_org(
        session, org_id=principal.org_id, user_id=principal.user_id
    )
    return dept_ids or None


async def list_partner_activity_feed(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID,
    limit: int = 20,
    locale: str = "vi",
) -> list[dict]:
    """Newest-first org activity, filtered by the viewer's own grants (and, as an
    approximation, department when the viewer is department-scoped)."""

    rows = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.actor_org_id == org_id)
            .order_by(AuditLog.occurred_at.desc())
            .limit(max(limit, 1) * 3)  # over-fetch; some rows get capability-filtered out
        )
    ).scalars().all()
    if not rows:
        return []

    # Org admins (wildcard grant) or anyone with an explicit members/roles grant
    # see the full org feed; a department-scoped member without that grant only
    # sees rows whose actor shares a department with them (see module docstring).
    is_org_wide = principal.is_superadmin or permission_checker.can(
        principal, "members", "read", resource_org_id=org_id
    )
    dept_ids = None if is_org_wide else await _viewer_department_ids(session, principal=principal)

    actor_dept_cache: dict[uuid.UUID, set[uuid.UUID]] = {}

    async def _actor_shares_department(actor_id: uuid.UUID | None) -> bool:
        if dept_ids is None:
            return True
        if actor_id is None:
            return False
        if actor_id not in actor_dept_cache:
            actor_dept_cache[actor_id] = await org_reporting_facade.department_ids_for_user_in_org(
                session, org_id=org_id, user_id=actor_id
            )
        return bool(actor_dept_cache[actor_id] & dept_ids)

    out: list[dict] = []
    for row in rows:
        cap = _capability_for(row.action)
        if cap is None:
            continue
        resource, action_verb = cap
        if not permission_checker.can(
            principal, resource, action_verb, resource_org_id=org_id
        ):
            continue
        if not await _actor_shares_department(row.actor_id):
            continue

        actor_name = None
        if row.actor_id is not None:
            actor = await user_service.get_by_id(session, row.actor_id)
            actor_name = actor.full_name if actor else None

        out.append({
            "action": row.action,
            "action_label": _label(row.action, locale=locale),
            "resource_type": row.resource_type,
            "resource_id": str(row.resource_id) if row.resource_id else None,
            "actor_name": actor_name,
            "occurred_at": row.occurred_at.isoformat(),
        })
        if len(out) >= limit:
            break
    return out

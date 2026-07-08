"""Idempotent starter-role seed for the university control plane (P2/WS2.4).

When the single university org is bootstrapped we also seed a handful of
ready-to-use, *editable* starter roles (Career Services, Moderation,
Partnerships, Analytics) so a superadmin/university admin can staff the org by
grant instead of building every role from scratch. These are plain
``is_system=False`` roles — an admin may customize or delete them; only the
``Admin`` role minted by :func:`organization_service.create_org_with_admin`
remains the immutable ``*:*`` system role.

Grants are drawn from the static ``PERMISSION_CATALOG`` (`domain/catalog.py`) —
no capability is ever hardcoded to a role *name* at enforcement time; these rows
are just convenient defaults. The seed is idempotent: it creates a role only if
no role with that name already exists in the org, and it never seeds a
non-university (partner) org.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.organization.domain.models import Organization, Permission, Role
from app.shared.audit import AuditContext, write_audit

_UNIVERSITY = "university"

# name -> (description, [(resource, action), ...]). Every tuple is a valid
# ``PERMISSION_CATALOG`` entry (validated by the seed test).
STARTER_UNIVERSITY_ROLES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "Career Services": (
        "Sinh viên & dịch vụ hướng nghiệp: cohort, hồ sơ rủi ro, duyệt CV, lịch hẹn.",
        [
            ("members", "read"),
            ("departments", "read"),
            ("career_services_cohorts", "read"),
            ("career_services_cohorts", "create"),
            ("career_services_cohorts", "update"),
            ("career_services_cohorts", "delete"),
            ("career_services_at_risk", "read"),
            ("career_services_at_risk", "create"),
            ("career_services_at_risk", "update"),
            ("career_services_cv_review", "read"),
            ("career_services_cv_review", "create"),
            ("career_services_cv_review", "update"),
            ("career_services_cv_review", "assign"),
            ("career_services_appointments", "read"),
            ("career_services_appointments", "create"),
            ("career_services_appointments", "update"),
            ("career_services_appointments", "cancel"),
            ("career_services_notes", "read"),
            ("career_services_notes", "create"),
            ("career_services_notes", "update"),
            ("career_services_interventions", "read"),
            ("career_services_interventions", "create"),
            ("career_services_interventions", "update"),
            ("career_services_reporting", "read"),
        ],
    ),
    "Moderation": (
        "Kiểm duyệt tin tuyển dụng, sự kiện, quảng cáo, đánh giá và quản trị phân loại ngành.",
        [
            ("members", "read"),
            ("jobs", "read"),
            ("jobs", "moderate"),
            ("events", "read"),
            ("events", "moderate"),
            ("advertising", "moderate"),
            ("reviews", "moderate"),
            ("abuse", "read"),
            ("abuse", "triage"),
            ("abuse", "escalate"),
            ("taxonomy", "manage"),
            ("audit", "read"),
        ],
    ),
    "Partnerships": (
        "Quan hệ đối tác: duyệt/từ chối hồ sơ đối tác, quản lý quan hệ, xem tin & sự kiện.",
        [
            ("members", "read"),
            ("partners", "read"),
            ("partners", "approve"),
            ("partners", "reject"),
            ("partners", "manage"),
            ("jobs", "read"),
            ("events", "read"),
            ("analytics", "view_job_metrics"),
            ("analytics", "export"),
        ],
    ),
    "Analytics": (
        "Báo cáo & phân tích: chỉ số tin tuyển dụng, lượt xem, xuất dữ liệu, nhật ký kiểm toán.",
        [
            ("members", "read"),
            ("analytics", "view_job_metrics"),
            ("analytics", "view_clicks"),
            ("analytics", "export"),
            ("audit", "read"),
            ("career_services_reporting", "read"),
        ],
    ),
}


async def ensure_university_starter_roles(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    ctx: RequestContext,
) -> int:
    """Create any missing starter roles for a **university** org. Returns the
    number of roles created (0 on re-run / for a non-university org).

    No commit — the caller owns the transaction (so this composes atomically with
    :func:`organization_service.create_university_org`). Idempotent by role name.
    """

    org_type = (
        await session.execute(
            select(Organization.org_type).where(Organization.id == org_id)
        )
    ).scalar_one_or_none()
    if org_type != _UNIVERSITY:
        return 0  # never seed a partner org

    existing_names = set(
        (
            await session.execute(
                select(Role.name).where(Role.org_id == org_id)
            )
        ).scalars().all()
    )

    audit_ctx = AuditContext(actor_id=actor_id, actor_org_id=org_id,
                             ip=ctx.ip, user_agent=ctx.user_agent)
    created = 0
    for name, (description, grants) in STARTER_UNIVERSITY_ROLES.items():
        if name in existing_names:
            continue
        role = Role(
            org_id=org_id, name=name, description=description, is_system=False
        )
        session.add(role)
        await session.flush()
        for resource, action in grants:
            session.add(
                Permission(role_id=role.id, resource_type=resource, action=action)
            )
        await session.flush()
        await write_audit(
            session, action="role.created", resource_type="role",
            resource_id=role.id, context=audit_ctx,
            after={
                "name": name,
                "via": "university_starter_seed",
                "permissions": sorted(f"{r}:{a}" for r, a in grants),
            },
        )
        created += 1
    return created

"""Candidate ownership (assignee) for multi-person recruiting teams.

An enterprise recruiting team routes each candidate to an accountable recruiter.
``assign_application`` sets (or clears, when ``assignee_membership_id`` is ``None``)
the durable owner on the application — distinct from ``candidate_stages.entered_by``
(who last moved the card). RBAC + tenant isolation reuse the SAME partner-of-org
gate as every other recruitment write (``decision_service._load_partner_application``:
cross-org is a ``404``); the action additionally requires ``applications:update``.

The assignee must be an ACTIVE member of the SAME org (validated through the org
read facade, never by importing the ``Membership`` ORM across the boundary). Every
change is audited and the newly-assigned recruiter gets an identity-safe in-app
feed row (the candidate may be anonymous — the notification never carries PII).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import feed_service
from app.modules.organization.application import org_reporting_facade
from app.modules.recruitment.application import _shared, decision_service
from app.modules.recruitment.application.errors import InvalidApplicationFieldError
from app.shared.audit import write_audit
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE


async def assign_application(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    assignee_membership_id: uuid.UUID | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Assign (or clear) the recruiter who owns this candidate.

    ``assignee_membership_id=None`` unassigns. A non-member / cross-org / inactive
    membership is rejected as an invalid field (422), never a tenant leak.
    """

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(principal, _RESOURCE, "update", resource_org_id=app.org_id)

    before = str(app.assigned_to_membership_id) if app.assigned_to_membership_id else None
    brief = None
    if assignee_membership_id is not None:
        brief = await org_reporting_facade.member_brief(
            session, org_id=app.org_id, membership_id=assignee_membership_id
        )
        if brief is None or not brief.active:
            # The assignee must be an ACTIVE member of THIS org. Anything else
            # (unknown id, cross-org membership, suspended/left member) is an
            # invalid assignee, reported as a field error — never a 404 that would
            # confirm another org's membership id exists.
            raise InvalidApplicationFieldError(field="assignee_membership_id")

    assigning = assignee_membership_id is not None
    app.assigned_to_membership_id = assignee_membership_id
    app.assigned_at = _shared.now() if assigning else None
    app.version += 1
    await session.flush()

    after_id = str(assignee_membership_id) if assigning else None
    await write_audit(
        session,
        action="application.assigned" if assigning else "application.unassigned",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        before={"assigned_to_membership_id": before},
        after={"assigned_to_membership_id": after_id},
    )

    if brief is not None:
        # Identity-safe: the candidate may be anonymous, so the feed row carries no
        # applicant PII — only the application pointer + job for the recruiter.
        await _notify_assignee(session, app=app, brief=brief, locale=locale)

    projection = await decision_service._partner_projection(
        session, app=app, principal=principal, locale=locale
    )
    await session.commit()
    return projection


async def _notify_assignee(session: AsyncSession, *, app, brief, locale: str) -> None:
    try:
        await feed_service.create_in_app(
            session,
            recipient_id=brief.user_id,
            notif_type="recruitment.candidate_assigned",
            action_url=f"/partner/applications/{app.id}",
            variables={"application_id": str(app.id)},
            locale=locale,
        )
    except Exception:  # noqa: BLE001 — a feed failure must never break the assignment write
        pass

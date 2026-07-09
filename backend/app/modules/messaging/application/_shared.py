"""Internal helpers shared across the messaging services.

Tenant/participant isolation follows the project pattern: a caller outside a thread
(wrong org, non-participant) gets ``404`` (never ``403``) so threads are not
enumerable (ADR-0012 §5, mirroring jobs/recruitment).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.messaging.domain import rules
from app.modules.messaging.domain.models import (
    MessageThread,
    MessageThreadParticipant,
)
from app.modules.organization.application import org_reporting_facade
from app.modules.users.application import user_read_facade
from app.shared.audit import AuditContext
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal

RESOURCE = "messaging"

# Priority for collapsing a user's many identities into the single persona that
# matters for the messaging matrix. An INSTITUTIONAL identity always wins so a
# university staffer / partner member who also holds the baseline ``student``
# identity (every account gets one at registration) is treated institutionally —
# the student↔student block targets users who are ONLY student-side.
_PERSONA_PRIORITY = (
    rules.UNIVERSITY_STAFF,
    rules.PARTNER_MEMBER,
    rules.ALUMNI,
    rules.STUDENT,
)


def effective_persona(personas: list[str]) -> str:
    for candidate in _PERSONA_PRIORITY:
        if candidate in personas:
            return candidate
    return rules.STUDENT


async def resolve_effective_personas(
    session: AsyncSession, user_ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, str], set[uuid.UUID]]:
    """Return ({user_id: effective_persona}, {org_ids the users belong to}).

    A user with no identity row is treated as ``student`` (the most restrictive
    assumption) so the student↔student block can never be bypassed.
    """

    by_user: dict[uuid.UUID, list[str]] = {}
    org_ids: set[uuid.UUID] = set()
    if user_ids:
        identities = await user_read_facade.get_identities_for_users(session, user_ids)
        for identity in identities:
            by_user.setdefault(identity.user_id, []).append(identity.persona)
            if identity.org_id is not None:
                org_ids.add(identity.org_id)
    resolved = {uid: effective_persona(by_user.get(uid, [])) for uid in user_ids}
    return resolved, org_ids


def now() -> datetime:
    return datetime.now(tz=UTC)


def as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def start_of_utc_day(at: datetime | None = None) -> datetime:
    at = at or now()
    return at.replace(hour=0, minute=0, second=0, microsecond=0)


def next_utc_midnight(at: datetime | None = None) -> datetime:
    from datetime import timedelta

    return start_of_utc_day(at) + timedelta(days=1)


def use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


def audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def load_thread(
    session: AsyncSession, *, thread_id: uuid.UUID, lock: bool = False
) -> MessageThread:
    stmt = select(MessageThread).where(
        MessageThread.id == thread_id, MessageThread.deleted_at.is_(None)
    )
    if lock and use_for_update():
        stmt = stmt.with_for_update()
    thread = (await session.execute(stmt)).scalar_one_or_none()
    if thread is None:
        raise ResourceNotFoundError()
    return thread


async def get_participant(
    session: AsyncSession, *, thread_id: uuid.UUID, user_id: uuid.UUID
) -> MessageThreadParticipant | None:
    return (
        await session.execute(
            select(MessageThreadParticipant).where(
                MessageThreadParticipant.thread_id == thread_id,
                MessageThreadParticipant.user_id == user_id,
                MessageThreadParticipant.removed_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def list_participants(
    session: AsyncSession, *, thread_id: uuid.UUID
) -> list[MessageThreadParticipant]:
    return list(
        (
            await session.execute(
                select(MessageThreadParticipant).where(
                    MessageThreadParticipant.thread_id == thread_id,
                    MessageThreadParticipant.removed_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )


async def org_type(session: AsyncSession, org_id: uuid.UUID | None) -> str | None:
    return await org_reporting_facade.org_type_for(session, org_id)


async def org_display_name(session: AsyncSession, org_id: uuid.UUID) -> str:
    name = await org_reporting_facade.display_name_for(session, org_id)
    return name or "VinUni Career"


async def is_university_moderator(session: AsyncSession, principal: Principal) -> bool:
    """A superadmin, or a ``university_staff`` member of a ``university``-type org."""

    if principal.is_superadmin:
        return True
    if principal.persona != "university_staff":
        return False
    return await org_type(session, principal.org_id) == "university"

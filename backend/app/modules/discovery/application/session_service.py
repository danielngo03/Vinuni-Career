"""First-party anonymous discovery session: get-or-create, signal merge, reset.

The session stores ONLY allowlisted coarse signals (privacy is enforced in
:mod:`app.modules.discovery.domain.allowlist`, not here). Functions are flush-only
unless documented otherwise — the caller (the event-ingest orchestrator or the
router) owns the commit, so the session upsert and the event insert commit
atomically.

No PII is logged or audited. The control-plane privacy action (``reset``) writes a
metadata-only audit row; the high-volume get-or-create / signal-merge path is part
of the analytics ledger itself and is not separately audited.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.discovery.domain import allowlist
from app.modules.discovery.domain.models import DiscoverySession
from app.shared.audit import AuditContext, write_audit
from app.shared.permissions import Principal


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _ttl() -> timedelta:
    return timedelta(days=get_settings().discovery_session_ttl_days)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite reads timestamps back naive; coerce to UTC-aware for comparison."""

    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _parse_cookie_id(cookie_id: str | None) -> uuid.UUID | None:
    if not cookie_id:
        return None
    try:
        return uuid.UUID(str(cookie_id).strip())
    except (ValueError, AttributeError):
        return None


async def _load_live(
    session: AsyncSession, *, session_id: uuid.UUID | None, now: datetime
) -> DiscoverySession | None:
    if session_id is None:
        return None
    row = (
        await session.execute(select(DiscoverySession).where(DiscoverySession.id == session_id))
    ).scalar_one_or_none()
    if row is None:
        return None
    expires = _aware(row.expires_at)
    if expires is not None and expires <= now:
        return None  # expired → treat as absent (cleanup sweep will prune it)
    return row


async def get_or_create(
    session: AsyncSession,
    *,
    cookie_id: str | None,
    locale: str | None = None,
    principal: Principal | None = None,
    now: datetime | None = None,
) -> DiscoverySession:
    """Resolve the discovery session for a cookie id, creating one if needed.

    A valid, live cookie session is refreshed (``last_seen_at`` + TTL extension,
    optional ``locale`` set, and ``user_id`` linked once the holder authenticates).
    An invalid/expired/missing cookie yields a brand-new random session. Flush-only.
    """

    now = now or _now()
    existing = await _load_live(session, session_id=_parse_cookie_id(cookie_id), now=now)
    user_id = principal.user_id if principal and principal.is_authenticated else None

    if existing is not None:
        existing.last_seen_at = now
        existing.expires_at = now + _ttl()
        if locale and not existing.locale:
            existing.locale = locale[:10]
        if user_id is not None and existing.user_id is None:
            existing.user_id = user_id
        await session.flush()
        return existing

    fresh = DiscoverySession(
        id=uuid.uuid4(),
        user_id=user_id,
        locale=locale[:10] if locale else None,
        coarse_tags={},
        opt_out=False,
        created_at=now,
        last_seen_at=now,
        expires_at=now + _ttl(),
    )
    session.add(fresh)
    await session.flush()
    return fresh


async def get_coarse_tags(
    session: AsyncSession, *, cookie_id: str | None, now: datetime | None = None
) -> dict:
    """Read-only resolve of a session's stored coarse signals (no write/commit).

    Used by the public delivery surfaces (recommendations rail, marketplace
    overview) to personalize a GET from the guest's first-party session WITHOUT
    mutating it. Returns ``{}`` for a missing/expired/opted-out session — the
    ranker then honestly falls back to ``recent``/``popular`` (no fabricated
    personalization). Never returns PII (``coarse_tags`` is allowlisted by
    construction).
    """

    now = now or _now()
    existing = await _load_live(session, session_id=_parse_cookie_id(cookie_id), now=now)
    if existing is None or existing.opt_out:
        return {}
    return dict(existing.coarse_tags or {})


def resolve_session_id(cookie_id: str | None) -> uuid.UUID | None:
    """Public wrapper: parse the first-party discovery cookie into a session id.

    Used by delivery routers (recommendations, marketplace overview) that need
    the raw session id — not just the coarse tags — to key sponsored-slot
    frequency capping (see ``frequency_cap.over_capped_placements``).
    """

    return _parse_cookie_id(cookie_id)


async def record_signal(
    session: AsyncSession,
    discovery_session: DiscoverySession,
    *,
    tags: dict,
) -> None:
    """Merge allowlisted coarse signals into the session. Flush-only.

    No-op when the session has opted out of personalization. Privacy is enforced
    by :func:`allowlist.merge_coarse_tags`: only allowlisted keys can survive.
    """

    if discovery_session.opt_out:
        return
    merged = allowlist.merge_coarse_tags(discovery_session.coarse_tags, tags)
    if merged != discovery_session.coarse_tags:
        discovery_session.coarse_tags = merged
        await session.flush()


async def reset(
    session: AsyncSession,
    *,
    cookie_id: str | None,
    principal: Principal | None = None,
    opt_out: bool = False,
    ctx: RequestContext | None = None,
    now: datetime | None = None,
) -> DiscoverySession | None:
    """Clear stored coarse signals (and optionally opt out). Commits.

    Honors the privacy reset/clear preference (spec §3). Returns the cleared
    session, or ``None`` if the cookie referenced no live session. Writes a
    metadata-only audit row (no PII, no coarse tags in the snapshot).
    """

    now = now or _now()
    existing = await _load_live(session, session_id=_parse_cookie_id(cookie_id), now=now)
    if existing is None:
        return None

    existing.coarse_tags = {}
    existing.opt_out = bool(opt_out) or existing.opt_out
    existing.last_seen_at = now
    await session.flush()
    await write_audit(
        session,
        action="discovery.session_reset",
        resource_type="discovery_session",
        resource_id=existing.id,
        context=AuditContext(
            actor_id=principal.user_id if principal else None,
            ip=ctx.ip if ctx else None,
            user_agent=ctx.user_agent if ctx else None,
        ),
        after={"opt_out": existing.opt_out, "signals_cleared": True},
    )
    await session.commit()
    return existing

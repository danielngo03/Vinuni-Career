"""Platform-wide stale mock-interview session sweeper (P0-3).

``MAX_SESSION_SECONDS`` / ``IDLE_TIMEOUT_SECONDS`` are advertised caps, but they
were only enforced LAZILY: the next ``create_session`` for the SAME user expired
that user's own abandoned rows. An abandoned ``active`` session for a student who
never returns lingered forever — inflating governance "active" counts and, via
the one-active-per-user partial index, potentially blocking that student's next
session.

This periodic sweeper expires abandoned ``active`` sessions PLATFORM-WIDE,
mirroring the lazy per-user cutoff in ``session_service.create_session``
(``MAX_SESSION_SECONDS`` + grace) but for every user. A session past the hard cap
plus a short grace can never legitimately take another turn
(``session_service._assert_within_caps`` hard-stops at the cap), so it is safe to
expire.

Registered on the periodic scheduler (``automation.scheduler.jobs``). Idempotent:
a re-tick finds only newly-stale rows; a session still within the cap (legitimately
mid-turn) is never touched.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mock_interview.application import caps
from app.modules.mock_interview.domain.models import (
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    MockInterviewSession,
)

logger = logging.getLogger(__name__)

# Grace beyond the hard session cap before an abandoned ``active`` row is expired.
# Matches the lazy per-user recovery cutoff used in ``create_session``.
STALE_GRACE_SECONDS = 120


async def sweep_stale_active(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Expire abandoned ``active`` sessions platform-wide. Returns ``{"expired": n}``.

    A session started before ``now - (MAX_SESSION_SECONDS + STALE_GRACE_SECONDS)``
    is abandoned (it cannot take another turn under the caps) and is transitioned
    ``active -> expired`` with ``ended_at`` stamped. The caller (the scheduler)
    owns the surrounding commit. Emits a leak-safe log line when anything expires.
    """

    now = now or datetime.now(tz=UTC)
    cutoff = now - timedelta(seconds=caps.MAX_SESSION_SECONDS + STALE_GRACE_SECONDS)
    stmt = (
        update(MockInterviewSession)
        .where(
            MockInterviewSession.status == STATUS_ACTIVE,
            MockInterviewSession.started_at < cutoff,
        )
        .values(status=STATUS_EXPIRED, ended_at=now)
    )
    result = await session.execute(stmt)
    # ``rowcount`` lives on CursorResult; the async execute return type is the
    # narrower ``Result``, so read it defensively for the type checker.
    expired = int(getattr(result, "rowcount", 0) or 0)
    if expired:
        logger.info("mock_interview.stale_session_sweep", extra={"expired": expired})
    return {"expired": expired}

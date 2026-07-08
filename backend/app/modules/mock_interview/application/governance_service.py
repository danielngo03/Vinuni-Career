"""University governance reads for mock interview (aggregate, masked).

University staff monitor the feature WITHOUT seeing named transcripts: aggregate
usage, completion, modality mix, and safety-flag COUNTS. Gated by the
``mock_interview`` RBAC noun AND the ``org_type == "university"`` check, so a
partner Admin's wildcard grant cannot reach it. No PII, no provider/model, no
transcript content is ever returned here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.realtime import current as realtime_current
from app.modules.mock_interview.application import caps
from app.modules.mock_interview.infrastructure import repository as repo
from app.modules.organization.application import org_reporting_facade
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "mock_interview"


async def _require_university(
    session: AsyncSession, principal: Principal, action: str
) -> None:
    """Superadmin, or a university-org member holding ``mock_interview:{action}``.

    The ``org_type == "university"`` gate blocks a partner Admin's ``*:*`` wildcard
    (mirrors ``partner_registration_service._require_university_actor``).
    """

    if principal.is_superadmin:
        return
    permission_checker.require(principal, _RESOURCE, action)
    if not await org_reporting_facade.is_university_org(session, principal.org_id):
        from app.shared.exceptions import PermissionDeniedError

        raise PermissionDeniedError(details={"reason": "university_only"})


async def stats(
    session: AsyncSession, *, principal: Principal, days: int = 30
) -> dict[str, Any]:
    """Aggregate mock-interview usage over the last ``days`` (privacy-safe)."""

    await _require_university(session, principal, "read")
    days = max(1, min(365, days))
    since = datetime.now(tz=UTC) - timedelta(days=days)
    agg = await repo.aggregate_stats(session, since=since)
    total = agg["total"]
    completed = agg["completed"]
    agg["completion_rate"] = round(completed / total, 3) if total else 0.0
    agg["window_days"] = days
    return agg


async def config(session: AsyncSession, *, principal: Principal) -> dict[str, Any]:
    """Read-only view of the effective caps + realtime availability (masked).

    Exposes no provider/model identity — only leak-safe operational limits.
    """

    await _require_university(session, principal, "read")
    return {
        "daily_session_cap": caps.DAILY_SESSION_CAP,
        "weekly_session_cap": caps.WEEKLY_SESSION_CAP,
        "max_session_seconds": caps.MAX_SESSION_SECONDS,
        "max_questions": caps.MAX_QUESTIONS,
        "target_questions": caps.DEFAULT_TARGET_QUESTIONS,
        "realtime_voice_enabled": bool(realtime_current().enabled),
    }

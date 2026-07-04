"""Single source of truth for the *public job visibility* SQL predicate.

The marketplace, company directory, and public-read facade must all use the
**exact** same definition of "a job a guest may discover" as
:func:`job_service.list_public_jobs`, otherwise the public surfaces drift out of
sync (e.g. the directory's ``active_job_count`` counting jobs the list would not
show). The predicate (``docs/BUSINESS_LOGIC.md`` §5) is factored here so there is
only one place to change it.

A job is publicly visible to a principal of ``levels`` when it is:

- not soft-deleted;
- ``active`` status + ``approved`` moderation;
- published (``published_at`` set);
- within an allowed visibility tier for the principal;
- not past its application deadline.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, or_

from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job


def guest_levels() -> frozenset[str]:
    """Visibility tiers an unauthenticated guest may discover (public-tier only)."""

    return lifecycle.visible_levels_for("guest", is_authenticated=False)


def apply_visible_filter(stmt: Select, *, levels: frozenset[str], now: datetime) -> Select:
    """Constrain ``stmt`` (selecting from :class:`Job`) to publicly visible rows."""

    return stmt.where(
        Job.deleted_at.is_(None),
        Job.status == lifecycle.ACTIVE,
        Job.moderation_status == lifecycle.MOD_APPROVED,
        Job.published_at.isnot(None),
        Job.visibility.in_(levels),
        or_(
            Job.application_deadline.is_(None),
            Job.application_deadline > now,
        ),
    )

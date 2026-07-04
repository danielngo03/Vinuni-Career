"""Shared dashboard helpers: failure-tolerant widget execution + small caps."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

# Small-list caps for the glance surfaces.
RECENT_CAP = 5
RECOMMENDED_CAP = 4


def empty_rows() -> list[dict]:
    """A fresh, correctly-typed empty list for failure-tolerant list widgets."""

    return []


async def safe[T](
    session: AsyncSession,
    factory: Callable[[], Awaitable[T]],
    *,
    fallback: T,
) -> T:
    """Run one dashboard widget, degrading to ``fallback`` on any failure.

    A widget is a read-only sub-query. If it raises, we roll the read transaction
    back (so a poisoned transaction does not cascade into the next widget) and
    return the widget's empty/null fallback. The dashboard envelope is therefore
    always well-formed; a single failing widget never 500s the page.

    RBAC gating is performed by the caller *before* any ``safe`` call, so a 401/403
    is never swallowed here.
    """

    try:
        return await factory()
    except Exception:  # noqa: BLE001 — intentional: degrade one widget, never the page
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass
        return fallback

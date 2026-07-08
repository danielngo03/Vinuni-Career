"""Recommendation snapshot sink (spec §8: ``recommendation_snapshots``).

Persists WHAT a guest/student was shown at a recommendation-serving point — the
ordered job ids, the honest per-item source, the product score, and the user-safe
reason codes — as a privacy-safe audit/repro/eval substrate. It is deliberately
best-effort: a snapshot write MUST NEVER break or slow down the serving path, so a
failure rolls back only the snapshot and returns ``None``.

Privacy contract (mirrors the discovery allowlist discipline):

- NO PII is stored — no name/email/phone, no exact location, no raw IP.
- reason codes are whitelisted to coarse ranking outputs; CV-identifying fields
  (``cv_id`` / ``cv_title``) and any free text are stripped, so no CV analytics
  leak into the snapshot (``.claude/rules`` data-engineer clause).
- ``scope`` (anonymous|session|user) is derived server-side from the principal +
  session — never trusted from the client.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.discovery.domain.models import RecommendationSnapshot
from app.shared.permissions import Principal

# The ONLY surfaces that persist a snapshot (real recommendation-serving points).
SNAPSHOT_SURFACES: frozenset[str] = frozenset(
    {"marketplace_overview", "jobs_recommendations"}
)

# Whitelisted, privacy-safe reason-code fields kept in a snapshot. cv_id / cv_title
# and any other key are dropped (no CV analytics / free text in the snapshot).
_SAFE_REASON_KEYS: frozenset[str] = frozenset(
    {"code", "value", "term", "skills", "days", "score"}
)


def _safe_reason(reason: Any) -> dict[str, Any] | None:
    if not isinstance(reason, dict) or "code" not in reason:
        return None
    return {k: v for k, v in reason.items() if k in _SAFE_REASON_KEYS}


def _safe_items(items: list[dict] | None) -> list[dict]:
    """Reduce presented items to the privacy-safe ranking outputs worth persisting."""

    out: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        job_id = item.get("id")
        if not job_id:
            continue
        reasons = [
            safe
            for safe in (_safe_reason(r) for r in item.get("reason_codes") or [])
            if safe is not None
        ]
        out.append(
            {
                "job_id": str(job_id),
                "source": item.get("source"),
                "score": item.get("score"),
                "reason_codes": reasons,
                "placement_id": item.get("placement_id"),
            }
        )
    return out


def _resolve_scope(
    principal: Principal | None, discovery_session_id: uuid.UUID | None
) -> tuple[str, uuid.UUID | None, uuid.UUID | None]:
    """Return ``(scope, session_id, user_id)`` — derived, never client-trusted."""

    if principal is not None and principal.is_authenticated:
        return "user", discovery_session_id, principal.user_id
    if discovery_session_id is not None:
        return "session", discovery_session_id, None
    return "anonymous", None, None


async def record_serving_snapshot(
    session: AsyncSession,
    *,
    surface: str,
    principal: Principal | None,
    discovery_session_id: uuid.UUID | None,
    list_source: str,
    personalized: bool,
    items: list[dict],
) -> RecommendationSnapshot | None:
    """Persist one recommendation snapshot. Best-effort; commits its own row.

    Returns ``None`` (and rolls back only the snapshot) on any failure or when the
    surface is not a real serving point / there is nothing to record — the serving
    response is unaffected.
    """

    if surface not in SNAPSHOT_SURFACES:
        return None
    safe_items = _safe_items(items)
    if not safe_items:
        return None

    scope, session_id, user_id = _resolve_scope(principal, discovery_session_id)
    snapshot = RecommendationSnapshot(
        id=uuid.uuid4(),
        surface=surface,
        list_source=list_source,
        personalized=bool(personalized),
        scope=scope,
        session_id=session_id,
        user_id=user_id,
        items=safe_items,
        item_count=len(safe_items),
    )
    try:
        session.add(snapshot)
        await session.commit()
    except Exception:  # noqa: BLE001 — an audit-snapshot write never breaks serving
        await session.rollback()
        return None
    return snapshot

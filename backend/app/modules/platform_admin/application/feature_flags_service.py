"""Platform Admin — Feature Flag service (P5).

Rules:
  - Superadmin-only for all write operations (re-checked here as defence-in-depth).
  - Every write is audited within the same transaction (atomic).
  - Duplicate key → ConflictError (user-safe, no DB internals in message).
  - Invalid rollout (outside 0-100) → ValidationFailedError.
  - Invalid key format → ValidationFailedError.
  - Missing flag for update → ResourceNotFoundError.

Key format: lowercase letters, digits, dots, underscores, and hyphens;
  must be non-empty and not start/end with a separator.
  Examples: "cv_studio.ai_rewrite", "jobs.competition_intelligence", "beta-2026"

evaluate():
  Pure function (no DB) used by feature-gated code paths elsewhere.

  - enabled=False → False (always)
  - enabled=True, rollout_percentage >= 100 → True (always)
  - enabled=True, rollout_percentage <= 0 → False
  - enabled=True, 1-99 → deterministic per-subject SHA-256 bucket
  - subject_key is None with partial rollout → False (conservative; document it)

  The bucketing is: int(sha256(subject_key.encode()).hexdigest(), 16) % 100 < rollout_percentage
  This is stable: same subject always lands in same bucket for a given percentage.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.platform_admin.domain.models import FeatureFlag
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*[a-z0-9]$|^[a-z0-9]$")


def _require_superadmin(principal: Principal) -> None:
    if not principal.is_superadmin:
        raise PermissionDeniedError()


def _validate_key(key: str) -> None:
    """Validate flag key format.

    Allowed: lowercase letters, digits, dots, underscores, hyphens.
    Must be non-empty; must not start or end with a separator character.
    """
    if not key or not _KEY_RE.match(key):
        raise ValidationFailedError(
            "Flag key must be non-empty and use only lowercase letters, digits, "
            "dots, underscores, or hyphens, and may not start or end with a separator."
        )


def _validate_rollout(rollout_percentage: int) -> None:
    if not (0 <= rollout_percentage <= 100):
        raise ValidationFailedError("rollout_percentage must be between 0 and 100.")


def _flag_to_dict(flag: FeatureFlag) -> dict[str, Any]:
    return {
        "id": str(flag.id),
        "key": flag.key,
        "description": flag.description,
        "enabled": flag.enabled,
        "rollout_percentage": flag.rollout_percentage,
        "updated_by": str(flag.updated_by) if flag.updated_by else None,
        "created_at": flag.created_at.isoformat(),
        "updated_at": flag.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Public service API
# ---------------------------------------------------------------------------


async def list_flags(session: AsyncSession) -> list[dict[str, Any]]:
    """Return all feature flags sorted by key. No RBAC gate here; callers
    (router) must enforce superadmin.
    """
    result = await session.execute(select(FeatureFlag).order_by(FeatureFlag.key))
    flags = result.scalars().all()
    return [_flag_to_dict(f) for f in flags]


async def create_flag(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: AuditContext,
    key: str,
    description: str = "",
    enabled: bool = False,
    rollout_percentage: int = 0,
) -> dict[str, Any]:
    """Create a new feature flag.

    Validates key format and rollout range. Duplicate key raises ConflictError
    with a user-safe message (no DB constraint text exposed). Audited atomically.
    """
    _require_superadmin(principal)
    _validate_key(key)
    _validate_rollout(rollout_percentage)

    flag = FeatureFlag(
        key=key,
        description=description,
        enabled=enabled,
        rollout_percentage=rollout_percentage,
        updated_by=principal.user_id,
    )
    session.add(flag)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise ConflictError("A feature flag with this key already exists.") from None

    # Refresh to pick up server-side created_at/updated_at before snapshotting.
    await session.refresh(flag)
    after = _flag_to_dict(flag)
    await write_audit(
        session,
        action="feature_flag.created",
        resource_type="feature_flag",
        resource_id=flag.id,
        context=ctx,
        before=None,
        after=after,
    )
    await session.commit()
    return after


async def update_flag(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: AuditContext,
    flag_id: uuid.UUID,
    **fields: Any,
) -> dict[str, Any]:
    """Partial update of a feature flag.

    Allowed fields: ``enabled``, ``description``, ``rollout_percentage``.
    Unknown fields are silently ignored. Audited atomically.
    """
    _require_superadmin(principal)

    result = await session.execute(select(FeatureFlag).where(FeatureFlag.id == flag_id))
    flag = result.scalar_one_or_none()
    if flag is None:
        raise ResourceNotFoundError("Feature flag not found.")

    before = _flag_to_dict(flag)

    if "enabled" in fields:
        flag.enabled = bool(fields["enabled"])
    if "description" in fields:
        flag.description = str(fields["description"])
    if "rollout_percentage" in fields:
        _validate_rollout(int(fields["rollout_percentage"]))
        flag.rollout_percentage = int(fields["rollout_percentage"])

    flag.updated_by = principal.user_id
    await session.flush()
    # Refresh to pick up server-side updated_at before snapshotting.
    await session.refresh(flag)

    after = _flag_to_dict(flag)
    await write_audit(
        session,
        action="feature_flag.updated",
        resource_type="feature_flag",
        resource_id=flag.id,
        context=ctx,
        before=before,
        after=after,
    )
    await session.commit()
    return after


def evaluate(flag: FeatureFlag, *, subject_key: str | None = None) -> bool:
    """Evaluate a feature flag for an optional subject.

    Bucketing strategy:
      - If ``enabled`` is False: always False.
      - If ``rollout_percentage >= 100`` and ``enabled``: always True.
      - If ``rollout_percentage <= 0``: always False.
      - Partial (1-99): deterministic bucketing via SHA-256 of ``subject_key``.
        ``int(sha256(subject_key.encode()).hexdigest(), 16) % 100 < rollout_percentage``
      - ``subject_key`` is None with partial rollout: returns False (conservative).
        This ensures unidentified callers never get partial-rollout access.
    """
    if not flag.enabled:
        return False
    pct = flag.rollout_percentage
    if pct >= 100:
        return True
    if pct <= 0:
        return False
    # Partial rollout — need a subject key for bucketing.
    if subject_key is None:
        return False
    bucket = int(hashlib.sha256(subject_key.encode()).hexdigest(), 16) % 100
    return bucket < pct

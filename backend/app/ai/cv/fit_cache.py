"""Redis hot cache for deterministic CV-job fit scores (job-list badges).

Key format:  fit:v2:{user_id}:{job_id}
TTL:         14 400 s (4 h)  — a backstop only; correctness comes from ``sig``.

SELF-VALIDATING: every cached entry carries a ``sig`` string built by the caller
from ``{SCORER_VERSION}:{job_version}:{cv_library_signature}``. ``get_cached``
returns the entry only when the caller's current ``sig`` matches the stored one,
so ANY change to the scorer, the job (``job.version``), or the user's CV library
(each CV's ``version``) makes the entry a miss and forces a recompute — exactly
"recompute only when the CV or JD changes", with no reliance on remembering to
call an invalidation hook. The explicit ``invalidate_*`` helpers below remain as
a best-effort fast-path purge but are no longer required for correctness.

The ``v1`` -> ``v2`` prefix bump abandons the old unversioned entries on deploy.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

FIT_KEY_PREFIX = "fit:v2"
FIT_TTL = 14_400  # 4 hours


def _key(user_id: uuid.UUID, job_id: uuid.UUID) -> str:
    return f"{FIT_KEY_PREFIX}:{user_id}:{job_id}"


async def get_cached(redis: Any, user_id: uuid.UUID, job_id: uuid.UUID, *, sig: str) -> dict | None:
    """Return the cached fit result, or None on miss / stale-sig / decode error.

    ``sig`` is the caller's current content signature; a stored entry whose
    signature differs is treated as a miss (its CV/JD/scorer version moved).
    """
    raw = await redis.get(_key(user_id, job_id))
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("sig") != sig:
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


async def set_cached(
    redis: Any, user_id: uuid.UUID, job_id: uuid.UUID, data: dict, *, sig: str
) -> None:
    """Store a fit result + its content signature with the standard TTL."""
    payload = json.dumps({"sig": sig, "data": data})
    await redis.setex(_key(user_id, job_id), FIT_TTL, payload)


async def invalidate_user(redis: Any, user_id: uuid.UUID) -> None:
    """Invalidate all scores for a user (e.g. when their CV changes).

    Uses SCAN with a per-iteration count cap to avoid blocking the Redis event
    loop on large key-spaces.
    """
    pattern = f"{FIT_KEY_PREFIX}:{user_id}:*"
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
        if keys:
            await redis.delete(*keys)
        if cursor == 0:
            break


async def invalidate_job(redis: Any, job_id: uuid.UUID) -> None:
    """Invalidate all user scores for a job (e.g. when job is updated).

    Uses SCAN to avoid KEYS blocking on production key-spaces.
    """
    pattern = f"{FIT_KEY_PREFIX}:*:{job_id}"
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
        if keys:
            await redis.delete(*keys)
        if cursor == 0:
            break

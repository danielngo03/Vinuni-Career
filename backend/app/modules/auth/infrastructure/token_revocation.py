"""Access-token (JTI) revocation denylist.

On logout we deny the current access-token ``jti`` immediately rather than wait
for its 15-minute expiry. Redis is the primary store (TTL-bounded); when Redis is
unavailable we fall back to an in-process set so local dev and tests work without
Redis. The authoritative session-level revocation is still ``sessions.revoked_at``
(checked on every request); this denylist is the fast path for single-token
logout (``docs/ARCHITECTURE.md`` §5).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "auth:revoked_jti:"
# Process-local fallback denylist: jti -> expiry timestamp.
_fallback: dict[str, float] = {}


def _redis_client():
    try:
        import redis.asyncio as aioredis

        return aioredis.from_url(get_settings().redis_url, socket_connect_timeout=1)
    except Exception:  # pragma: no cover - redis optional locally
        return None


async def revoke_jti(jti: uuid.UUID, *, expires_at: datetime) -> None:
    ttl = max(int((expires_at - datetime.now(tz=UTC)).total_seconds()), 1)
    key = f"{_KEY_PREFIX}{jti}"
    client = _redis_client()
    if client is not None:
        try:
            await client.set(key, "1", ex=ttl)
            await client.aclose()
            return
        except Exception:
            logger.info("auth.revocation_redis_unavailable_fallback")
    _fallback[str(jti)] = expires_at.timestamp()


async def is_revoked(jti: uuid.UUID) -> bool:
    key = f"{_KEY_PREFIX}{jti}"
    client = _redis_client()
    if client is not None:
        try:
            exists = await client.exists(key)
            await client.aclose()
            return bool(exists)
        except Exception:
            logger.info("auth.revocation_redis_unavailable_fallback")
    expiry = _fallback.get(str(jti))
    if expiry is None:
        return False
    if expiry < datetime.now(tz=UTC).timestamp():
        _fallback.pop(str(jti), None)
        return False
    return True


def reset_fallback() -> None:
    """Test helper: clear the in-process denylist."""

    _fallback.clear()

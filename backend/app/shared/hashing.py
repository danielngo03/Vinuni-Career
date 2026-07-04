"""Privacy-safe hashing and device-hint derivation.

Raw IPs, raw user agents, and raw refresh tokens are never stored. We persist
SHA-256 hashes plus a coarse, non-identifying device hint.
"""

from __future__ import annotations

import hashlib

from app.core.config import get_settings


def _salt() -> str:
    # Reuse the JWT secret as a hashing salt so hashes are not portable across
    # deployments. This is sufficient for audit correlation, not for reversal.
    return get_settings().jwt_secret_key


def hash_value(value: str | None) -> str | None:
    """Return a salted SHA-256 hex digest, or ``None`` for empty input."""

    if not value:
        return None
    digest = hashlib.sha256(f"{_salt()}:{value}".encode())
    return digest.hexdigest()


def hash_ip(ip: str | None) -> str | None:
    return hash_value(ip)


def hash_user_agent(user_agent: str | None) -> str | None:
    return hash_value(user_agent)


def device_hint(user_agent: str | None) -> str:
    """Derive a coarse, non-PII device hint from a user-agent string.

    Returns values like ``chrome_desktop`` / ``safari_mobile`` — never the raw
    user agent. Safe to display on account/device settings screens.
    """

    if not user_agent:
        return "unknown"
    ua = user_agent.lower()

    if "edg/" in ua:
        browser = "edge"
    elif "chrome" in ua and "chromium" not in ua:
        browser = "chrome"
    elif "firefox" in ua:
        browser = "firefox"
    elif "safari" in ua:
        browser = "safari"
    else:
        browser = "browser"

    if any(token in ua for token in ("mobile", "iphone", "android")):
        platform = "mobile"
    elif "ipad" in ua or "tablet" in ua:
        platform = "tablet"
    else:
        platform = "desktop"

    return f"{browser}_{platform}"

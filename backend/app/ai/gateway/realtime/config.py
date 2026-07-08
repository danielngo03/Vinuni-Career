"""Realtime provider configuration snapshot (leak-safe).

Mirrors ``runtime_config`` for the realtime tier: an in-memory, ORM-free view of
the current realtime settings. Bootstrapped from env; a superadmin registry may
``publish`` an override later (same one-way module→infra pattern). No API keys or
base URLs are ever stored here — only leak-safe aliases + booleans.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True, slots=True)
class RealtimeConfig:
    enabled: bool
    provider: str  # registry alias, e.g. "gemini-live" (never a vendor string to clients)
    model: str  # internal model id (never serialized to clients)
    voice: str  # provider voice name (internal)
    ttl_seconds: int


_override: RealtimeConfig | None = None


def _bootstrap_from_env() -> RealtimeConfig:
    s = get_settings()
    return RealtimeConfig(
        enabled=bool(s.ai_realtime_enabled),
        provider=(s.ai_realtime_provider or "").strip(),
        model=(s.ai_realtime_model or "").strip(),
        voice=(s.ai_realtime_voice or "").strip(),
        ttl_seconds=int(s.ai_realtime_ttl_seconds or 660),
    )


def current() -> RealtimeConfig:
    return _override if _override is not None else _bootstrap_from_env()


def publish(cfg: RealtimeConfig) -> None:
    """Install a resolved snapshot (superadmin registry is the only writer)."""

    global _override
    _override = cfg


def reset_to_bootstrap() -> None:
    """Test seam: drop any published snapshot and fall back to live env."""

    global _override
    _override = None

"""Best-effort Langfuse tracing client.

Design constraints
------------------
- Complete no-op when keys are absent or the ``langfuse`` package is not installed.
- NEVER raises; any error is logged at WARNING level and returns None.
- NEVER sends prompt text, response text, API keys, base URLs, or any PII in
  trace metadata.
- Lazily imports the Langfuse SDK so the module loads cleanly in environments
  where the package is not installed (unit tests, lightweight deploys).
- ``_settings_keys()`` is the single source of key resolution — monkeypatch it
  in tests to control enabled/disabled state without touching Settings or env.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _settings_keys() -> tuple[str | None, str | None, str | None]:
    """Return ``(secret_key, public_key, base_url)`` from application settings.

    Returns ``(None, None, None)`` on any error so the caller degrades gracefully.
    This function is the single key-resolution point; tests monkeypatch it to
    force disabled/enabled state without importing real settings or real keys.
    """
    try:
        from app.core.config import get_settings

        s = get_settings()
        return s.langfuse_secret_key, s.langfuse_public_key, s.langfuse_base_url
    except Exception:  # noqa: BLE001
        return None, None, None


def is_enabled() -> bool:
    """Return True only when all three Langfuse credentials are present."""
    secret_key, public_key, base_url = _settings_keys()
    return bool(secret_key and public_key and base_url)


def trace_call(
    *,
    task_type: str,
    alias: str,
    provider: str | None,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    status: str,
    org_id: str | None,
    user_id: str | None,
    request_id: str,
) -> str | None:
    """Record a metadata-only AI call trace to Langfuse.

    Returns the trace id string on success, or ``None`` when disabled or on any
    error.  Never raises.  Never includes prompt text, response text, API keys,
    base URLs, or raw PII in the trace payload.

    Parameters mirror the fields in ``ai_usage_log``; provider/model are
    function-slot aliases (e.g. ``"chat_default"``), never raw vendor strings.
    """
    if not is_enabled():
        return None

    secret_key, public_key, base_url = _settings_keys()

    try:
        # Lazy import so the module is importable even when langfuse is absent.
        from langfuse import Langfuse  # type: ignore[import]

        client = Langfuse(  # type: ignore[misc]
            secret_key=secret_key,
            public_key=public_key,
            host=base_url,
        )

        # Metadata-only: no prompt, no response, no raw keys, no base URL.
        # provider/model are slot aliases (e.g. "chat_default"), not raw
        # vendor/model strings.  Org/user ids are internal UUIDs — not names
        # or emails.
        metadata = {
            "task_type": task_type,
            "alias": alias,
            "provider_alias": provider,
            "model_alias": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "latency_ms": latency_ms,
            "status": status,
            "org_id": org_id,
            "user_id": user_id,
            "request_id": request_id,
        }

        # Langfuse v4 (OpenTelemetry-based): use start_as_current_observation
        # context manager to create a span and obtain its trace id.
        trace_id: str | None = None
        with client.start_as_current_observation(  # type: ignore[misc]
            name=f"ai_call.{task_type}",
            metadata=metadata,
        ):
            trace_id = client.get_current_trace_id()  # type: ignore[misc]

        client.flush()  # type: ignore[misc]
        return trace_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("langfuse trace_call failed (non-fatal): %s", exc)
        return None

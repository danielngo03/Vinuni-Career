"""Gateway runner for grounded single-shot AI tasks (CV + JD + recruiter notes).

Every generation routes its model call through here so that: (1) all LLM access
goes through the gateway/factory (offline by default), (2) the output guard
scrubs provider/model/token internals from any model text, (3) usage is tracked
PII-safely, and (4) provider failures degrade to a friendly ``AI_UNAVAILABLE``
error instead of a stack trace (``docs/EDGE_CASES_FAILURE_MODES.md``).

Metering: when a caller passes ``db`` (an async session), the call runs through
the full :class:`AiTaskRunner` governance pipeline — budget pre-check, input
guard, ops telemetry, ``ai_usage_log`` row (attributed to ``user_id``/``org_id``),
and, when a ``usage_context`` is supplied, a durable **billable-ledger charge**
of ``charge_units`` cost-weighted credits on the successful, user-visible result
(``docs/PRODUCT_OPERATING_MODEL.md`` §3). Without ``db`` the legacy direct path
runs (offline/sync/no-principal contexts and tests) — log-only, no charge.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import TYPE_CHECKING

from app.ai.gateway import runtime_config
from app.ai.gateway.base import AIMessage
from app.ai.gateway.factory import get_provider
from app.ai.gateway.output_guard import guard_completion
from app.ai.observability.usage import log_ai_usage
from app.shared.exceptions import AIUnavailableError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.ai.observability.billable_usage import UsageContext


def _messages(system_prompt: str, user_content: str) -> list[AIMessage]:
    # STATIC system prefix first (cache-eligible), dynamic content after (§8.2).
    return [
        AIMessage(role="system", content=system_prompt),
        AIMessage(role="user", content=user_content),
    ]


async def _record_ledger(
    db: AsyncSession,
    usage_context: UsageContext | None,
    *,
    result_status: str,
    base_units: int,
) -> None:
    """Best-effort billable-ledger write — never breaks the AI path."""
    if usage_context is None:
        return
    try:
        from app.ai.observability.billable_usage import record_billable_usage

        await record_billable_usage(
            db, ctx=usage_context, result_status=result_status, base_units=base_units
        )
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger("ai.cv.llm").warning(
            "ai_billable_ledger_write_failed", exc_info=True
        )


async def generate_note(
    *,
    task_type: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.2,
    max_tokens: int = 512,
    db: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    usage_context: UsageContext | None = None,
    charge_units: int = 0,
) -> str:
    """Run a single grounded completion and return SCRUBBED, user-safe text.

    The returned text is used only as an advisory note/rationale — never as the
    source of CV/JD facts (those are grounded deterministically by the task
    layer).
    """

    alias = runtime_config.current().chat_model_alias
    messages = _messages(system_prompt, user_content)

    if db is not None:
        # Metered path — the runner charges the ledger on success itself (plain
        # text is the user-visible product, so provider-success == chargeable).
        from app.ai.gateway.task_runner import AiTaskRunner

        runner = AiTaskRunner(
            db,
            alias=alias,
            task_type=task_type,
            user_id=user_id,
            session_id=session_id,
            org_id=org_id,
            usage_context=usage_context,
            charge_units=charge_units,
        )
        completion = await runner.complete(
            messages, temperature=temperature, max_tokens=max_tokens
        )
        return completion.text

    # Legacy no-db path (offline/sync/no-principal): direct provider, log-only.
    provider = get_provider()
    try:
        completion = await provider.complete(
            messages, alias=alias, temperature=temperature, max_tokens=max_tokens
        )
    except Exception as exc:  # provider/network failure -> friendly fallback
        log_ai_usage(task_type=task_type, alias=alias, success=False)
        raise AIUnavailableError() from exc

    text = guard_completion(completion)  # drops usage/model_alias, scrubs leaks
    log_ai_usage(
        task_type=task_type,
        alias=alias,
        success=True,
        prompt_chars=len(system_prompt) + len(user_content),
        completion_chars=len(text),
    )
    return text


def _extract_json(raw: str) -> dict:
    """Extract and parse JSON from LLM output.

    Handles: raw JSON, markdown fenced blocks (```json ... ```), and extra
    whitespace. Raises ``ValueError`` if no valid JSON object is found.
    """
    text = raw.strip()
    # Strip optional markdown fences
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()
    # Find the outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in LLM output")
    return json.loads(text[start : end + 1])


async def generate_json_note(
    *,
    task_type: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.2,
    max_tokens: int = 1500,
    db: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    usage_context: UsageContext | None = None,
    charge_units: int = 0,
) -> dict:
    """Run a single completion that expects a JSON-object response.

    Strips markdown fences, extracts the outermost JSON object, and parses it.
    Raises ``AIUnavailableError`` on provider failure OR on malformed JSON (so
    callers can safely fall back without crashing). On the metered path the
    ledger is charged ONLY on a successfully-parsed result — a provider failure
    records ``provider_failed`` and a JSON parse failure records
    ``validation_failed`` (both 0 credits).
    """
    alias = runtime_config.current().chat_model_alias
    messages = _messages(system_prompt, user_content)

    if db is not None:
        from app.ai.gateway.task_runner import AiTaskRunner

        # No usage_context on the runner — we charge manually below, gated on a
        # successfully-parsed JSON result (the runner would otherwise charge on
        # mere provider success, double-charging unusable output).
        runner = AiTaskRunner(
            db,
            alias=alias,
            task_type=task_type,
            user_id=user_id,
            session_id=session_id,
            org_id=org_id,
        )
        try:
            completion = await runner.complete(
                messages, temperature=temperature, max_tokens=max_tokens
            )
        except AIUnavailableError:
            await _record_ledger(
                db, usage_context, result_status="provider_failed", base_units=0
            )
            raise
        try:
            data = _extract_json(completion.text)
        except (ValueError, json.JSONDecodeError) as exc:
            await _record_ledger(
                db, usage_context, result_status="validation_failed", base_units=0
            )
            raise AIUnavailableError() from exc
        await _record_ledger(
            db, usage_context, result_status="success", base_units=charge_units
        )
        return data

    # Legacy no-db path.
    provider = get_provider()
    try:
        completion = await provider.complete(
            messages, alias=alias, temperature=temperature, max_tokens=max_tokens
        )
    except Exception as exc:
        log_ai_usage(task_type=task_type, alias=alias, success=False)
        raise AIUnavailableError() from exc

    text = guard_completion(completion)
    log_ai_usage(
        task_type=task_type,
        alias=alias,
        success=True,
        prompt_chars=len(system_prompt) + len(user_content),
        completion_chars=len(text),
    )
    try:
        return _extract_json(text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AIUnavailableError() from exc

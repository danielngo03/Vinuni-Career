"""Gateway runner for CV AI tasks.

Every CV AI generation routes its model call through here so that: (1) all LLM
access goes through the gateway/factory (offline by default), (2) the output guard
scrubs provider/model/token internals from any model text, (3) usage is tracked
PII-safely through the usage-aware governance path (budget pre-check + durable
``ai_usage_log`` ledger + ops telemetry) when an :class:`AiUsageContext` is
supplied, and (4) provider failures degrade to a friendly ``AI_UNAVAILABLE``
error instead of a stack trace (``docs/EDGE_CASES_FAILURE_MODES.md``).

``get_provider()`` is called directly (rather than via ``AiTaskRunner``) on
purpose: it is the offline-eval patch point, and CV facts are grounded
deterministically so these calls must NOT run input-policy rewriting (which would
change offline outputs). The governance wrapper adds budget/ledger/telemetry
*around* the unchanged provider call. When no context is passed, behaviour is
identical to the legacy metadata-only log line.
"""

from __future__ import annotations

import json
import re
import time

from app.ai.gateway import runtime_config
from app.ai.gateway.base import AIMessage
from app.ai.gateway.factory import get_provider
from app.ai.gateway.governance import precheck_budget, record_usage
from app.ai.gateway.output_guard import guard_completion
from app.ai.gateway.usage_context import AiUsageContext
from app.shared.exceptions import AIUnavailableError


async def _governed_completion(
    *,
    task_type: str,
    system_prompt: str,
    user_content: str,
    temperature: float,
    max_tokens: int,
    usage: AiUsageContext | None,
) -> str:
    """Run one grounded completion through the usage-aware governance path.

    Returns SCRUBBED, user-safe text. Raises ``AIUnavailableError`` on provider
    failure and ``PaymentRequiredError`` (propagated) on budget refusal.
    """

    alias = runtime_config.current().chat_model_alias
    messages = [
        # STATIC system prefix first (cache-eligible), dynamic content after (§8.2).
        AIMessage(role="system", content=system_prompt),
        AIMessage(role="user", content=user_content),
    ]
    prompt_chars = len(system_prompt) + len(user_content)

    # 1. Budget pre-check (no-op offline / without a db session). A 402 refusal
    #    must propagate — record a blocked telemetry span, then re-raise.
    try:
        await precheck_budget(
            usage, alias=alias, prompt_chars=prompt_chars, max_tokens=max_tokens
        )
    except Exception:
        await record_usage(
            usage,
            task_type=task_type,
            alias=alias,
            success=False,
            prompt_chars=prompt_chars,
            status="blocked",
            write_ledger=False,
        )
        raise

    provider = get_provider()  # offline by default; eval/test patch point
    t0 = time.monotonic()
    try:
        completion = await provider.complete(
            messages, alias=alias, temperature=temperature, max_tokens=max_tokens
        )
    except Exception as exc:  # provider/network failure -> friendly fallback
        latency_ms = int((time.monotonic() - t0) * 1000)
        await record_usage(
            usage,
            task_type=task_type,
            alias=alias,
            success=False,
            prompt_chars=prompt_chars,
            latency_ms=latency_ms,
            status="error",
        )
        raise AIUnavailableError() from exc

    latency_ms = int((time.monotonic() - t0) * 1000)
    text = guard_completion(completion)  # drops usage/model_alias, scrubs leaks
    await record_usage(
        usage,
        task_type=task_type,
        alias=alias,
        success=True,
        prompt_chars=prompt_chars,
        completion_chars=len(text),
        prompt_tokens=completion.usage.get("prompt_tokens"),
        completion_tokens=completion.usage.get("completion_tokens"),
        latency_ms=latency_ms,
        status="ok",
    )
    return text


async def generate_note(
    *,
    task_type: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.2,
    max_tokens: int = 512,
    usage: AiUsageContext | None = None,
) -> str:
    """Run a single grounded completion and return SCRUBBED, user-safe text.

    The returned text is used only as an advisory note/rationale — never as the
    source of CV facts (those are grounded deterministically by the task layer).

    Pass ``usage`` (an :class:`AiUsageContext` carrying a db session + attribution)
    to route the call through the full budget/ledger/telemetry path. Without it,
    the call is only metadata-logged (legacy behaviour, e.g. sync/background).
    """

    return await _governed_completion(
        task_type=task_type,
        system_prompt=system_prompt,
        user_content=user_content,
        temperature=temperature,
        max_tokens=max_tokens,
        usage=usage,
    )


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
    usage: AiUsageContext | None = None,
) -> dict:
    """Run a single completion that expects a JSON-object response.

    Strips markdown fences, extracts the outermost JSON object, and parses it.
    Raises ``AIUnavailableError`` on provider failure OR on malformed JSON
    (so callers can safely fall back without crashing).
    """

    text = await _governed_completion(
        task_type=task_type,
        system_prompt=system_prompt,
        user_content=user_content,
        temperature=temperature,
        max_tokens=max_tokens,
        usage=usage,
    )
    try:
        return _extract_json(text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AIUnavailableError() from exc

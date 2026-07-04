"""Gateway runner for CV AI tasks.

Every CV AI generation routes its model call through here so that: (1) all LLM
access goes through the gateway/factory (offline by default), (2) the output guard
scrubs provider/model/token internals from any model text, (3) usage is tracked
PII-safely, and (4) provider failures degrade to a friendly ``AI_UNAVAILABLE``
error instead of a stack trace (``docs/EDGE_CASES_FAILURE_MODES.md``).
"""

from __future__ import annotations

import json
import re

from app.ai.gateway import runtime_config
from app.ai.gateway.base import AIMessage
from app.ai.gateway.factory import get_provider
from app.ai.gateway.output_guard import guard_completion
from app.ai.observability.usage import log_ai_usage
from app.shared.exceptions import AIUnavailableError


async def generate_note(
    *,
    task_type: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.2,
    max_tokens: int = 512,
) -> str:
    """Run a single grounded completion and return SCRUBBED, user-safe text.

    The returned text is used only as an advisory note/rationale — never as the
    source of CV facts (those are grounded deterministically by the task layer).
    """

    alias = runtime_config.current().chat_model_alias
    messages = [
        # STATIC system prefix first (cache-eligible), dynamic content after (§8.2).
        AIMessage(role="system", content=system_prompt),
        AIMessage(role="user", content=user_content),
    ]
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
) -> dict:
    """Run a single completion that expects a JSON-object response.

    Strips markdown fences, extracts the outermost JSON object, and parses it.
    Raises ``AIUnavailableError`` on provider failure OR on malformed JSON
    (so callers can safely fall back without crashing).
    """
    alias = runtime_config.current().chat_model_alias
    messages = [
        AIMessage(role="system", content=system_prompt),
        AIMessage(role="user", content=user_content),
    ]
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

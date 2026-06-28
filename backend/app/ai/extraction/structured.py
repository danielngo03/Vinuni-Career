from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

from app.ai.gateway import ChatMessage, ChatRequest, get_llm_gateway
from app.ai.gateway.errors import LLMGatewayError


def extract_structured[ModelT: BaseModel](
    *,
    text: str,
    schema_model: type[ModelT],
    instruction: str,
    max_retries: int = 2,
) -> ModelT:
    schema = schema_model.model_json_schema()
    messages = [
        ChatMessage(
            role="system",
            content=(
                "You extract structured recruiting data. Return only JSON that conforms "
                "to the provided schema. Do not invent facts that are absent from source text."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"{instruction}\n\n"
                "JSON SCHEMA:\n"
                f"{json.dumps(schema, ensure_ascii=False)}\n\n"
                "SOURCE TEXT:\n"
                f"{text[:80_000]}"
            ),
        ),
    ]
    last_error = ""
    for attempt in range(max(1, max_retries)):
        request = ChatRequest(
            messages=messages
            if not last_error
            else [
                *messages,
                ChatMessage(
                    role="user",
                    content=(
                        "Your previous JSON failed validation. Fix it without adding new facts. "
                        f"Validation error: {last_error}"
                    ),
                ),
            ],
            temperature=0.0,
            response_format=_json_schema_response_format(schema_model.__name__, schema),
            response_schema=schema,
            metadata={"feature": "structured_extraction", "attempt": str(attempt + 1)},
        )
        try:
            response = get_llm_gateway().chat(request)
        except LLMGatewayError as exc:
            last_error = str(exc)
            continue
        if response.provider == "offline":
            raise ValueError(
                "Structured extraction requires a real LLM provider; offline fallback is disabled."
            )
        try:
            return schema_model.model_validate(_load_json_object(response.content))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = str(exc)
    raise ValueError(f"Structured extraction failed: {last_error}")


def _json_schema_response_format(name: str, schema: dict) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "schema": schema, "strict": True},
    }


def _load_json_object(content: str) -> dict:
    stripped = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    if not stripped.startswith("{"):
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in model output.")
        stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("Structured extraction requires a JSON object.")
    return payload

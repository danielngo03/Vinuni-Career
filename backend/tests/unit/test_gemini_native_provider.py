from __future__ import annotations

from app.ai.gateway.providers.gemini_native import GeminiNativeProvider
from app.ai.gateway.schemas import ChatMessage, ChatRequest


def test_chat_body_uses_json_schema_field_for_structured_output():
    provider = GeminiNativeProvider(
        base_url="https://example.test",
        api_key="test-key",
        chat_model="test-model",
        embedding_model="test-embedding",
        timeout_seconds=1,
    )
    schema = {
        "$defs": {
            "Nested": {
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "type": "object",
            }
        },
        "properties": {"nested": {"$ref": "#/$defs/Nested"}},
        "required": ["nested"],
        "type": "object",
    }

    body = provider._chat_body(
        ChatRequest(
            messages=[ChatMessage(role="user", content="Return structured data")],
            response_format={"type": "json_schema"},
            response_schema=schema,
        )
    )

    generation_config = body["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseJsonSchema"] == schema
    assert "responseSchema" not in generation_config

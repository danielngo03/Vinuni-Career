"""AI safety guards: input guard (pre-generation) and output guard.

The output guard lives in ``app.ai.gateway.output_guard`` (applied on every
gateway response). The input guard here neutralises prompt-injection and caps
length on free-text user input before it reaches the LLM (``docs/AI_PRODUCT_SPEC``
§9.1, ``.claude/rules/ai.md`` §9).
"""

"""Text-LLM structuring tier for JD extraction (text-only; secrets redacted).

Routes through the shared gateway JSON helper so provider/model/token internals
never leak and usage is tracked. Never receives raw bytes — only extracted text.
"""

from __future__ import annotations

from app.ai.cv.llm import generate_json_note  # generic gateway JSON helper
from app.ai.extraction.adapters.base import redact_secrets
from app.ai.prompts.jd_extraction import v3 as prompt


async def run_jd_text_structuring(text: str) -> dict:
    """Structure JD ``text`` into the v3 JSON field set. Raises AIUnavailableError."""
    safe = redact_secrets(text)
    return await generate_json_note(
        task_type="jd_extraction",
        system_prompt=prompt.TEXT_SYSTEM_PROMPT,
        user_content=prompt.build_text_user_message(safe),
        temperature=0.1,
        max_tokens=2200,
    )

"""Server-mediated Gemini voice tier (STT + TTS) for the mock interview.

This is the sanctioned home for the native Google GenAI SDK (``google-genai``),
per ``.claude/rules/ai.md`` ("no direct provider SDK calls in domain modules").
Domain code (``mock_interview``) calls :func:`synthesize` / :func:`transcribe`;
it never imports ``google.genai`` directly, and no vendor/model string is ever
returned to the student.
"""

from app.ai.gateway.speech.service import (
    SpeechUnavailableError,
    speech_enabled,
    synthesize,
    transcribe,
)

__all__ = [
    "SpeechUnavailableError",
    "speech_enabled",
    "synthesize",
    "transcribe",
]

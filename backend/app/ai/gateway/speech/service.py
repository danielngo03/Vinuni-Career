"""Gemini speech adapter: text→speech (TTS) and speech→text (STT).

Runs on a Google/Vertex GenAI key via ``google-genai``. On a Vertex *express*
API key the client is ``genai.Client(vertexai=True, api_key=...)``; the same code
serves an AI-Studio key when ``AI_SPEECH_USE_VERTEX=false``. Both TTS and STT go
through ``generateContent`` (audio-out / audio-in), so no realtime socket and no
service account are required.

Leak-safety: callers receive only audio bytes / transcript text. Model ids,
provider names, and token counts never leave this module — usage is logged as
metadata only (``ai_usage_log``) with a leak-safe alias.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import math
import uuid
import wave

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Leak-safe aliases surfaced in usage logs (never the concrete model id).
_TTS_ALIAS = "interview_tts"
_STT_ALIAS = "interview_stt"

# Energy base-unit derivation for the voice tiers (masked product currency).
# TTS is billed by synthesized characters (one unit per ~400 chars, min 1); STT
# is billed per transcribed answer (turn count). These are deterministic weights
# passed to the single energy settlement choke point so the voice tiers are
# metered, not invisible/uncapped.
_TTS_CHARS_PER_UNIT = 400

_PLACEHOLDERS = {"", "changeme", "your-key", "placeholder", "none", "null"}

# Gemini TTS returns raw little-endian PCM (L16) mono at 24 kHz. We wrap it in a
# WAV container so the browser <audio>/AudioContext can play it with no decoding.
_TTS_SAMPLE_RATE = 24000
_TTS_CHANNELS = 1
_TTS_SAMPLE_WIDTH = 2  # bytes (16-bit)


class SpeechUnavailableError(RuntimeError):
    """Raised when the speech tier is disabled, unconfigured, or the call fails.

    Carries only a leak-safe ``reason`` token — never a provider/model string.
    """

    def __init__(self, reason: str = "unavailable") -> None:
        self.reason = reason
        super().__init__(reason)


def _speech_key() -> str:
    """Resolve the Google GenAI key (same precedence as the realtime tier)."""

    import os

    s = get_settings()
    for candidate in (
        getattr(s, "gemini_api_key", "") or "",
        os.environ.get("GEMINI_API_KEY", ""),
        os.environ.get("GOOGLE_API_KEY", ""),
        os.environ.get("AI_PROVIDER_GEMINI_LIVE_API_KEY", ""),
    ):
        cand = (candidate or "").strip()
        if cand and cand.lower() not in _PLACEHOLDERS:
            return cand
    return ""


def speech_enabled() -> bool:
    """True when the tier is switched on AND a usable credential is present.

    A credential is either an API key (developer/express) OR a service-account
    ADC bound to a Vertex project.
    """

    import os

    s = get_settings()
    if not getattr(s, "ai_speech_enabled", False):
        return False
    if _speech_key():
        return True
    project = getattr(s, "google_cloud_project", "") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    cred = getattr(s, "google_application_credentials", "") or os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS", ""
    )
    return bool(getattr(s, "ai_speech_use_vertex", True) and cred and project)


_client_cache: object | None = None


def _client() -> object:
    """Lazily build and cache the GenAI client (import is deferred).

    Credential-flexible so any of the three supported setups "just works":

    1. **Service account / ADC on a real Vertex project** (production-grade,
       reliable, full quota; also the only path that unlocks Vertex partner
       models like ElevenLabs): ``AI_SPEECH_USE_VERTEX=true`` +
       ``GOOGLE_CLOUD_PROJECT`` + ``GOOGLE_APPLICATION_CREDENTIALS`` →
       ``genai.Client(vertexai=True, project=..., location=...)``.
    2. **AI Studio developer key** (simplest free path): ``AI_SPEECH_USE_VERTEX=
       false`` + ``GEMINI_API_KEY=AIza...`` → ``genai.Client(api_key=...)``.
    3. **Vertex express key** (``AQ...``): ``AI_SPEECH_USE_VERTEX=true`` + key →
       ``genai.Client(vertexai=True, api_key=...)`` (limited free quota).
    """

    import os

    global _client_cache
    if _client_cache is not None:
        return _client_cache
    try:
        from google import genai  # deferred import; heavy dep
    except Exception as exc:  # pragma: no cover - dependency missing
        raise SpeechUnavailableError("sdk_missing") from exc
    s = get_settings()
    use_vertex = bool(getattr(s, "ai_speech_use_vertex", True))
    project = (
        getattr(s, "google_cloud_project", "") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    ).strip()
    location = (
        getattr(s, "google_cloud_location", "")
        or os.environ.get("GOOGLE_CLOUD_LOCATION", "")
        or "us-central1"
    ).strip()
    # A service-account JSON path in settings/.env is exported into the process
    # env so google-auth ADC can find it, regardless of how the app was launched
    # (pydantic-settings does NOT populate os.environ on its own).
    cred_path = (
        getattr(s, "google_application_credentials", "")
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    ).strip()
    if cred_path and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
    has_adc = bool(cred_path)
    key = _speech_key()
    try:
        if use_vertex and has_adc and project:
            # Service-account / ADC path (reliable, full quota). api_key and
            # project/location are mutually exclusive, so ADC wins when present.
            _client_cache = genai.Client(vertexai=True, project=project, location=location)
        elif key:
            # Developer key (use_vertex=false) or Vertex express key.
            _client_cache = genai.Client(vertexai=use_vertex, api_key=key)
        else:
            raise SpeechUnavailableError("no_key")
    except SpeechUnavailableError:
        raise
    except Exception as exc:  # pragma: no cover - misconfig
        logger.warning("speech.client_init_failed", exc_info=True)
        raise SpeechUnavailableError("client_init") from exc
    return _client_cache


def _pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(_TTS_CHANNELS)
        w.setsampwidth(_TTS_SAMPLE_WIDTH)
        w.setframerate(_TTS_SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


async def _log_usage(
    session: object | None,
    *,
    task_type: str,
    alias: str,
    success: bool,
    chars: int,
    user_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
) -> None:
    """Best-effort metadata usage log; never raises, never blocks correctness."""

    if session is None:
        return
    try:
        from app.ai.observability.usage import log_ai_usage_async

        await log_ai_usage_async(
            session,  # type: ignore[arg-type]
            task_type=task_type,
            alias=alias,
            success=success,
            prompt_chars=chars,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:  # pragma: no cover - observability must never break calls
        logger.debug("speech.usage_log_failed", exc_info=True)


def _dedupe_digest(value: str | bytes) -> str:
    """Short stable digest used ONLY as an idempotency-key suffix.

    Keeps identical re-synthesis / re-transcription of the same content from
    double-charging, while distinct content charges separately. Never surfaced.
    """

    raw = value.encode("utf-8", "ignore") if isinstance(value, str) else value
    return hashlib.sha1(raw).hexdigest()[:16]


async def _settle_energy(
    session: object | None,
    *,
    kind: str,
    dedupe: str,
    base_units: int,
    user_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
) -> None:
    """Best-effort energy settlement for a successful voice-tier call.

    Mirrors :func:`_log_usage`: never raises, never blocks correctness. Routes the
    charge through the single settlement choke point (``energy_service.charge``)
    so the student's masked energy account reflects the voice tiers. Idempotent on
    a ``(session, kind, content-digest)`` key so a client retry never double
    charges. Degrades to a no-op — the ``ai_usage_log`` row already exists — when
    the billing module is unavailable at call time (cross-lane resilience).
    """

    if session is None or user_id is None or session_id is None:
        return
    try:
        from app.ai.observability.billable_usage import (
            FEATURE_INTERVIEW_SIM,
            PERSONA_STUDENT,
            RESULT_SUCCESS,
            SCOPE_USER,
            UsageContext,
            make_idempotency_key,
        )
        from app.modules.billing.application.energy_service import charge

        ctx = UsageContext(
            actor_persona=PERSONA_STUDENT,
            feature_key=FEATURE_INTERVIEW_SIM,
            task_type=f"mock_interview_{kind}",
            billing_scope=SCOPE_USER,
            actor_user_id=user_id,
            session_id=session_id,
            resource_type="mock_interview_session",
            resource_id=session_id,
            idempotency_key=make_idempotency_key(
                FEATURE_INTERVIEW_SIM, session_id, kind, dedupe
            ),
        )
        await charge(
            session,  # type: ignore[arg-type]
            ctx=ctx,
            result_status=RESULT_SUCCESS,
            base_units=max(1, int(base_units)),
        )
    except Exception:  # pragma: no cover - accounting must never break the call
        logger.debug("speech.energy_settle_skipped", exc_info=True)


async def synthesize(
    text: str,
    *,
    voice: str | None = None,
    session: object | None = None,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> tuple[bytes, str]:
    """Synthesize ``text`` to speech. Returns ``(wav_bytes, "audio/wav")``.

    Raises :class:`SpeechUnavailableError` when disabled/unconfigured/failed.
    """

    s = get_settings()
    if not getattr(s, "ai_speech_enabled", False):
        raise SpeechUnavailableError("disabled")
    clean = (text or "").strip()
    if not clean:
        raise SpeechUnavailableError("empty_text")
    # Output-guard the interviewer text BEFORE it is spoken: if a provider/model
    # string ever slipped into the turn, it must never be synthesized to audio.
    from app.ai.gateway.output_guard import scrub_text

    clean = scrub_text(clean).strip()
    if not clean:
        raise SpeechUnavailableError("empty_text")
    max_chars = int(getattr(s, "ai_speech_max_tts_chars", 1200))
    clean = clean[:max_chars]
    model = getattr(s, "ai_speech_tts_model", "gemini-2.5-flash-preview-tts")
    voice_name = voice or getattr(s, "ai_speech_voice", "Aoede")

    def _call() -> bytes:
        from google.genai import types

        client = _client()
        resp = client.models.generate_content(  # type: ignore[attr-defined]
            model=model,
            contents=clean,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                ),
            ),
        )
        part = resp.candidates[0].content.parts[0]
        data = part.inline_data.data
        if not data:
            raise SpeechUnavailableError("empty_audio")
        return data

    try:
        pcm = await asyncio.to_thread(_call)
    except SpeechUnavailableError:
        await _log_usage(
            session, task_type="mock_interview_tts", alias=_TTS_ALIAS,
            success=False, chars=len(clean), user_id=user_id, session_id=session_id,
        )
        raise
    except Exception as exc:
        logger.warning("speech.tts_failed", exc_info=True)
        await _log_usage(
            session, task_type="mock_interview_tts", alias=_TTS_ALIAS,
            success=False, chars=len(clean), user_id=user_id, session_id=session_id,
        )
        raise SpeechUnavailableError("tts_failed") from exc

    wav = _pcm_to_wav(pcm)
    await _log_usage(
        session, task_type="mock_interview_tts", alias=_TTS_ALIAS,
        success=True, chars=len(clean), user_id=user_id, session_id=session_id,
    )
    await _settle_energy(
        session,
        kind="tts",
        dedupe=_dedupe_digest(clean),
        base_units=max(1, math.ceil(len(clean) / _TTS_CHARS_PER_UNIT)),
        user_id=user_id,
        session_id=session_id,
    )
    return wav, "audio/wav"


async def transcribe(
    audio: bytes,
    mime_type: str,
    *,
    locale: str = "vi",
    session: object | None = None,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> str:
    """Transcribe spoken ``audio`` to text. Returns the transcript (may be empty).

    Raises :class:`SpeechUnavailableError` when disabled/unconfigured/failed.
    """

    s = get_settings()
    if not getattr(s, "ai_speech_enabled", False):
        raise SpeechUnavailableError("disabled")
    if not audio:
        raise SpeechUnavailableError("empty_audio")
    max_bytes = int(getattr(s, "ai_speech_max_audio_bytes", 8 * 1024 * 1024))
    if len(audio) > max_bytes:
        raise SpeechUnavailableError("audio_too_large")
    model = getattr(s, "ai_speech_stt_model", "gemini-2.5-flash")
    # The instruction is English (prompt-language rule); the CONTENT language is
    # whatever the student spoke. We ask for a verbatim transcript with no
    # commentary so the text can be fed straight into the turn engine.
    instruction = (
        "You are a speech transcriber. Transcribe the spoken audio VERBATIM in "
        "its original language. Output ONLY the transcript text with no quotes, "
        "labels, translation, or commentary. If there is no intelligible speech, "
        "output an empty string."
    )

    def _call() -> str:
        from google.genai import types

        client = _client()
        resp = client.models.generate_content(  # type: ignore[attr-defined]
            model=model,
            contents=[
                types.Part.from_bytes(data=audio, mime_type=mime_type),
                instruction,
            ],
        )
        return (resp.text or "").strip()

    try:
        text = await asyncio.to_thread(_call)
    except Exception as exc:
        logger.warning("speech.stt_failed", exc_info=True)
        await _log_usage(
            session, task_type="mock_interview_stt", alias=_STT_ALIAS,
            success=False, chars=0, user_id=user_id, session_id=session_id,
        )
        raise SpeechUnavailableError("stt_failed") from exc

    await _log_usage(
        session, task_type="mock_interview_stt", alias=_STT_ALIAS,
        success=True, chars=len(text), user_id=user_id, session_id=session_id,
    )
    # STT is billed per transcribed answer (one spoken turn = one unit).
    await _settle_energy(
        session,
        kind="stt",
        dedupe=_dedupe_digest(audio),
        base_units=1,
        user_id=user_id,
        session_id=session_id,
    )
    return text

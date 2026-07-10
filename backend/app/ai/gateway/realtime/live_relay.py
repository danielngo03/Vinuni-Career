"""Server-mediated Gemini Live relay for the mock interview (true realtime voice).

Unlike the AI-Studio ephemeral-token *browser-direct* tier, the browser here
cannot hold the Google service-account credential, so the SERVER brokers the
Live socket: it authenticates to Vertex Live with ADC, relays the student's mic
audio IN and the interviewer's native-audio OUT, and streams live transcripts.

This is the app's only server WebSocket bridge. Auth + session-owner scoping are
done by the caller (the WS route) BEFORE ``run_interview_live`` is invoked; this
module only bridges an already-authorized socket to the model. Leak-safe: the
browser sees audio + transcript text only — never a provider/model string.

Wire protocol (browser <-> server):
  browser -> server:
    * binary frame  = raw PCM16 mono 16 kHz mic audio
    * text  {"type":"activity_start"}   - student began speaking (push-to-talk)
    * text  {"type":"activity_end"}     - student stopped; model may now answer
    * text  {"type":"bye"}              - end the session
  server -> browser:
    * text  {"type":"ready"}
    * binary frame  = raw PCM16 mono 24 kHz interviewer audio (play it)
    * text  {"type":"input_transcript","text":...}   - what the student said
    * text  {"type":"output_transcript","text":...}  - what the interviewer said
    * text  {"type":"interrupted"}                    - barge-in; flush playback
    * text  {"type":"turn_complete"}
    * text  {"type":"error","reason":...}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from app.ai.gateway.output_guard import scrub_text

logger = logging.getLogger(__name__)

# A DB-free callback: the router passes this in and persists the just-completed
# turn(s) in a short session. Keeping persistence in the caller keeps this relay
# free of any DB import (it is the app's only server WS bridge).
OnTurn = Callable[[list[dict[str, str]]], Awaitable[None]]

SPEAKER_CANDIDATE = "candidate"
SPEAKER_INTERVIEWER = "interviewer"

# Kicks the interviewer off so it speaks the FIRST question without waiting for
# the student. English instruction (prompt-language rule); the interview persona
# + output language come from the grounded system instruction.
_KICKOFF = (
    "Begin the interview now: greet the candidate in one short sentence "
    "and ask your first question."
)


class LiveRelayUnavailable(RuntimeError):
    """Raised when the Live relay tier is disabled/unconfigured. Leak-safe reason."""

    def __init__(self, reason: str = "unavailable") -> None:
        self.reason = reason
        super().__init__(reason)


def live_relay_enabled() -> bool:
    """True when the relay is switched on AND a service-account credential + project
    are configured (the relay needs ADC — an API key cannot reach Vertex Live)."""

    from app.core.config import get_settings

    s = get_settings()
    if not bool(getattr(s, "ai_realtime_relay_enabled", False)):
        return False
    project = getattr(s, "google_cloud_project", "") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    cred = getattr(s, "google_application_credentials", "") or os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS", ""
    )
    return bool(project and cred)


def _build_client() -> Any:
    """Build the Vertex GenAI client (ADC, region-pinned to the Live region)."""

    from app.core.config import get_settings

    s = get_settings()
    cred = (
        getattr(s, "google_application_credentials", "")
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    ).strip()
    if cred and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred
    project = (
        getattr(s, "google_cloud_project", "") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    ).strip()
    location = (getattr(s, "ai_realtime_relay_location", "") or "us-central1").strip()
    if not (project and cred):
        raise LiveRelayUnavailable("no_credentials")
    try:
        from google import genai
    except Exception as exc:  # pragma: no cover - dependency missing
        raise LiveRelayUnavailable("sdk_missing") from exc
    return genai.Client(vertexai=True, project=project, location=location)


def _live_config(system_instruction: str, voice: str) -> Any:
    from google.genai import types

    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        # Push-to-talk: the client sends explicit activity_start/end, so the model
        # does not need server-side VAD and won't cut the student off mid-thought.
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
        ),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice),
            ),
        ),
        system_instruction=types.Content(parts=[types.Part(text=system_instruction)]),
    )


async def run_interview_live(
    ws: Any,
    *,
    system_instruction: str,
    voice: str,
    on_turn: OnTurn | None = None,
    max_seconds: int = 600,
) -> None:
    """Bridge an accepted WebSocket to a Gemini Live interview session.

    On EACH ``turn_complete`` (and once more on close for any tail) the just
    completed ``{"speaker","text"}`` turn(s) are handed to ``on_turn`` so the
    caller can persist them incrementally in a short DB session — a crash/kill
    mid-interview no longer loses the whole transcript. This relay stays DB-free:
    persistence lives entirely in the injected callback.

    The interviewer's transcript is output-guarded BEFORE it is streamed to the
    browser AND before it is accumulated for persistence, so a leaked
    provider/model string can never reach the student or the stored turn.

    Returns when either side closes or the hard ``max_seconds`` cap is hit. Never
    raises for a normal client disconnect.
    """

    from google.genai import types

    from app.core.config import get_settings

    s = get_settings()
    model = getattr(s, "ai_realtime_relay_model", "gemini-live-2.5-flash-native-audio")
    client = _build_client()

    cur_in: list[str] = []
    cur_out: list[str] = []

    async def _flush_turns() -> None:
        # Candidate text is the student's own speech (re-checked by the caller's
        # injection guard on persist). Interviewer text is model output: scrub the
        # JOINED text so a provider/model string split across streamed fragments
        # is still caught before it is stored.
        joined_in = "".join(cur_in).strip()
        joined_out = scrub_text("".join(cur_out).strip()).strip()
        batch: list[dict[str, str]] = []
        if joined_in:
            batch.append({"speaker": SPEAKER_CANDIDATE, "text": joined_in})
            cur_in.clear()
        if joined_out:
            batch.append({"speaker": SPEAKER_INTERVIEWER, "text": joined_out})
            cur_out.clear()
        if batch and on_turn is not None:
            try:
                await on_turn(batch)
            except Exception:  # noqa: BLE001 - persistence must not break the relay
                logger.warning("live_relay.on_turn_failed", exc_info=True)

    async with client.aio.live.connect(
        model=model, config=_live_config(system_instruction, voice)
    ) as sess:
        await ws.send_json({"type": "ready"})
        # Make the interviewer speak the first question immediately.
        await sess.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=_KICKOFF)])
        )

        async def client_to_live() -> None:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    return
                data = msg.get("bytes")
                if data is not None:
                    await sess.send_realtime_input(
                        audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                    )
                    continue
                text = msg.get("text")
                if text is None:
                    continue
                try:
                    payload = json.loads(text)
                except (ValueError, TypeError):
                    continue
                kind = payload.get("type")
                if kind == "activity_start":
                    await sess.send_realtime_input(activity_start=types.ActivityStart())
                elif kind == "activity_end":
                    await sess.send_realtime_input(activity_end=types.ActivityEnd())
                elif kind == "bye":
                    return

        async def live_to_client() -> None:
            # ``sess.receive()`` is a PER-TURN async generator: it completes when
            # the interviewer's current response ends. Loop so the relay spans the
            # whole multi-turn interview (each student answer triggers the next
            # turn); the outer task is cancelled when the client disconnects.
            while True:
                async for r in sess.receive():
                    if r.data:
                        await ws.send_bytes(r.data)
                    sc = r.server_content
                    if not sc:
                        continue
                    in_tx = getattr(sc, "input_transcription", None)
                    if in_tx and in_tx.text:
                        cur_in.append(in_tx.text)
                        await ws.send_json({"type": "input_transcript", "text": in_tx.text})
                    out_tx = getattr(sc, "output_transcription", None)
                    if out_tx and out_tx.text:
                        # Accumulate the RAW fragment for a join-then-scrub at
                        # flush; scrub the fragment separately for the live send.
                        cur_out.append(out_tx.text)
                        await ws.send_json(
                            {"type": "output_transcript", "text": scrub_text(out_tx.text)}
                        )
                    if getattr(sc, "interrupted", None):
                        await ws.send_json({"type": "interrupted"})
                    if getattr(sc, "turn_complete", None):
                        await _flush_turns()
                        await ws.send_json({"type": "turn_complete"})

        t_in = asyncio.create_task(client_to_live())
        t_out = asyncio.create_task(live_to_client())
        try:
            done, pending = await asyncio.wait(
                {t_in, t_out},
                timeout=max(30, int(max_seconds)),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            # Surface a real error (not a normal disconnect) if a pump crashed.
            for task in done:
                exc = task.exception()
                if exc is not None:
                    logger.warning("live_relay.pump_failed", exc_info=exc)
        finally:
            await _flush_turns()

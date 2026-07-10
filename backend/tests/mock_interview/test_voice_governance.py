"""Voice + realtime governance/safety (P0-4, P1-3).

Locks in the fixes for the audit findings on the voice tiers, WITHOUT touching a
real provider:

- Relay (P0-4): the just-completed turn(s) are handed to the ``on_turn`` callback
  on EVERY ``turn_complete`` (incremental persistence — a mid-interview crash no
  longer loses the transcript), once per turn.
- Relay (P1-3): the interviewer's transcript is output-guarded BEFORE it is
  streamed to the browser AND before it is accumulated for persistence, so a
  leaked provider/model string can never reach the student or the stored turn.
- TTS (P1-3): the interviewer text is output-guarded BEFORE synthesis, so a
  leaked provider/model string is never spoken.

These drive fakes (a scripted Live session, a fake TTS client), so no google
credential / network / DB is required.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from app.ai.gateway import speech
from app.ai.gateway.realtime import live_relay

_LEAK = "gemini"  # a forbidden provider/model term the guard must scrub


# --------------------------------------------------------------------------- #
# Relay fakes                                                                   #
# --------------------------------------------------------------------------- #
class _Tx:
    def __init__(self, text: str) -> None:
        self.text = text


class _SC:
    """Stand-in for a Live ``server_content`` chunk."""

    def __init__(
        self,
        *,
        input_text: str | None = None,
        output_text: str | None = None,
        turn_complete: bool = False,
        interrupted: bool = False,
    ) -> None:
        self.input_transcription = _Tx(input_text) if input_text is not None else None
        self.output_transcription = _Tx(output_text) if output_text is not None else None
        self.turn_complete = turn_complete
        self.interrupted = interrupted


class _Resp:
    def __init__(self, *, data: bytes | None = None, server_content: _SC | None = None) -> None:
        self.data = data
        self.server_content = server_content


async def _aiter(items):
    for it in items:
        yield it


async def _blocking_aiter():
    # Parks the ``live_to_client`` pump on the next turn until it is cancelled
    # (mirrors a real Live socket waiting for the model's next response).
    await asyncio.Event().wait()
    if False:  # pragma: no cover - never yields; makes this an async generator
        yield None


class _FakeSession:
    def __init__(self, turns: list[list[_Resp]]) -> None:
        self._turns = turns
        self._i = 0
        self.sent: list[tuple] = []

    async def send_client_content(self, *, turns) -> None:
        self.sent.append(("client_content", turns))

    async def send_realtime_input(self, **kw) -> None:
        self.sent.append(("realtime_input", kw))

    def receive(self):
        i = self._i
        self._i += 1
        if i < len(self._turns):
            return _aiter(self._turns[i])
        return _blocking_aiter()


class _ConnectCM:
    def __init__(self, sess: _FakeSession) -> None:
        self._sess = sess

    async def __aenter__(self) -> _FakeSession:
        return self._sess

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeClient:
    def __init__(self, sess: _FakeSession) -> None:
        self.aio = SimpleNamespace(live=SimpleNamespace(connect=lambda **kw: _ConnectCM(sess)))


class _FakeWS:
    """Records server->browser frames; says 'bye' once both turns are persisted."""

    def __init__(self, done: asyncio.Event) -> None:
        self.json_sent: list[dict] = []
        self.bytes_sent: list[bytes] = []
        self._done = done

    async def send_json(self, payload: dict) -> None:
        self.json_sent.append(payload)

    async def send_bytes(self, data: bytes) -> None:
        self.bytes_sent.append(data)

    async def receive(self) -> dict:
        await self._done.wait()
        return {"text": json.dumps({"type": "bye"})}


async def test_relay_persists_per_turn_and_scrubs_interviewer_output(monkeypatch):
    # Two turns; the interviewer output of turn 1 leaks a provider term split
    # across streamed fragments.
    turns = [
        [
            _Resp(server_content=_SC(input_text="I built REST APIs.")),
            _Resp(server_content=_SC(output_text=f"Nice, tell me about {_LEAK} ")),
            _Resp(server_content=_SC(output_text="in your project.")),
            _Resp(server_content=_SC(turn_complete=True)),
        ],
        [
            _Resp(server_content=_SC(input_text="Sure, happy to.")),
            _Resp(server_content=_SC(output_text="Thanks for sharing.")),
            _Resp(server_content=_SC(turn_complete=True)),
        ],
    ]
    sess = _FakeSession(turns)
    monkeypatch.setattr(live_relay, "_build_client", lambda: _FakeClient(sess))

    done = asyncio.Event()
    ws = _FakeWS(done)
    persisted: list[list[dict]] = []

    async def on_turn(batch: list[dict]) -> None:
        persisted.append(batch)
        if len(persisted) >= 2:
            done.set()

    await asyncio.wait_for(
        live_relay.run_interview_live(
            ws, system_instruction="You are an interviewer.", voice="Aoede",
            on_turn=on_turn, max_seconds=5,
        ),
        timeout=10,
    )

    # P0-4: on_turn fired once per turn_complete (incremental persistence).
    assert len(persisted) == 2
    turn1 = {t["speaker"]: t["text"] for t in persisted[0]}
    assert turn1["candidate"] == "I built REST APIs."
    # P1-3: the interviewer text persisted for turn 1 is scrubbed (join-then-scrub
    # catches the term even though it was split across fragments).
    assert _LEAK not in turn1["interviewer"].lower()
    assert "[hệ thống AI]" in turn1["interviewer"]

    # P1-3: the live browser frames never carry the leaked term either.
    for frame in ws.json_sent:
        if frame.get("type") == "output_transcript":
            assert _LEAK not in frame["text"].lower()


async def test_relay_tolerates_no_callback(monkeypatch):
    """A missing on_turn must not crash the relay (defensive default)."""

    turns = [[_Resp(server_content=_SC(output_text="Hello.", turn_complete=True))]]
    sess = _FakeSession(turns)
    monkeypatch.setattr(live_relay, "_build_client", lambda: _FakeClient(sess))

    done = asyncio.Event()
    ws = _FakeWS(done)
    done.set()  # allow the bye immediately; the single turn still flushes safely

    await asyncio.wait_for(
        live_relay.run_interview_live(
            ws, system_instruction="sys", voice="Aoede", on_turn=None, max_seconds=5,
        ),
        timeout=10,
    )
    assert any(f.get("type") == "ready" for f in ws.json_sent)


# --------------------------------------------------------------------------- #
# TTS fakes                                                                     #
# --------------------------------------------------------------------------- #
class _InlineData:
    def __init__(self, data: bytes) -> None:
        self.data = data


class _Part:
    def __init__(self, data: bytes) -> None:
        self.inline_data = _InlineData(data)


class _Content:
    def __init__(self, parts: list[_Part]) -> None:
        self.parts = parts


class _Cand:
    def __init__(self, content: _Content) -> None:
        self.content = content


class _TtsResp:
    def __init__(self, candidates: list[_Cand]) -> None:
        self.candidates = candidates


class _FakeTtsClient:
    def __init__(self, captured: dict) -> None:
        self._captured = captured

        class _Models:
            def generate_content(inner, *, model, contents, config):  # noqa: N805
                captured["contents"] = contents
                return _TtsResp([_Cand(_Content([_Part(b"\x00\x01\x02\x03")]))])

        self.models = _Models()


async def test_tts_output_guards_input_before_synthesis(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        speech.service, "get_settings", lambda: SimpleNamespace(ai_speech_enabled=True)
    )
    monkeypatch.setattr(speech.service, "_client", lambda: _FakeTtsClient(captured))

    # session=None keeps the call DB-free (usage-log + energy settle are no-ops).
    wav, mime = await speech.synthesize(
        f"You are speaking with {_LEAK}, a large model.", session=None
    )
    assert mime == "audio/wav"
    assert wav  # wrapped PCM->WAV bytes

    # The text actually sent to the synth is scrubbed — the provider term never
    # reaches the audio model.
    sent = captured["contents"]
    assert _LEAK not in sent.lower()
    assert "[hệ thống AI]" in sent


async def test_tts_rejects_empty_after_scrub(monkeypatch):
    # A body that is ONLY a provider term still must not synthesize an empty line;
    # the guard replaces it, so this stays non-empty — but a whitespace-only body
    # is rejected as empty_text up-front.
    monkeypatch.setattr(
        speech.service, "get_settings", lambda: SimpleNamespace(ai_speech_enabled=True)
    )
    with pytest.raises(speech.SpeechUnavailableError):
        await speech.synthesize("   ", session=None)

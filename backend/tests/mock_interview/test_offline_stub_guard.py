"""The OfflineProvider stub must never surface as an interviewer question.

When real AI calls are disabled the gateway resolves to the deterministic
``OfflineProvider``, whose ``"[offline] ... kiểm thử ... Yêu cầu: <echo>"`` scaffold
echoes the candidate's own input. Streaming that verbatim as the interviewer's
line is a leak of internal test scaffolding. ``stream_interviewer`` must instead
degrade to the static, human-quality fallback turn:

- primary guard: no real provider active -> static fallback (the default offline
  test environment, i.e. the exact production offline-fallback moment);
- defensive guard: even if a provider nominally claims to be "live" but the
  gateway still returns the offline stub, the first chunk is suppressed.

Neither the streamed tokens nor the persisted interviewer turn may contain the
``[offline]`` marker, the word ``kiểm thử``, or an echo of the candidate answer.
"""

from __future__ import annotations

import uuid

from app.ai.prompts.mock_interview import v1 as prompts
from app.modules.mock_interview.application import conversation_service, session_service
from app.modules.mock_interview.domain.models import SPEAKER_INTERVIEWER
from app.modules.mock_interview.infrastructure import repository as repo

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.mock_interview._seed import make_public_job, make_strong_cv

# A phrase unique to the candidate's answer — the offline stub echoes it back, so
# its absence in the interviewer output proves the stub was suppressed.
_ANSWER = "I built REST APIs with FastAPI and shipped them to production at Acme."
_ANSWER_ECHO = "shipped them to production at Acme"


async def _seed(db):
    _u, student = await make_student(db)
    await make_strong_cv(db, student)
    job_id = await make_public_job(db)
    created = await session_service.create_session(
        db, principal=student, ctx=CTX, job_id=job_id, cv_id=None
    )
    return student, uuid.UUID(created["session_id"])


async def _drain_turn(db, student, sid):
    return [
        e
        async for e in session_service.stream_turn(
            db, principal=student, session_id=sid, answer=_ANSWER
        )
    ]


def _assert_no_stub(events: list[dict]) -> None:
    for e in events:
        text = str(e.get("text") or "")
        assert "[offline]" not in text, f"leaked offline marker in {e['type']}: {text!r}"
        assert "kiểm thử" not in text, f"leaked offline scaffold in {e['type']}: {text!r}"
        assert _ANSWER_ECHO not in text, f"leaked answer echo in {e['type']}: {text!r}"


async def test_stream_turn_offline_uses_static_fallback_not_stub(db_session) -> None:
    """Offline provider active (default) -> the interviewer line is the static
    fallback, and no ``[offline]`` scaffold reaches the stream or storage."""

    student, sid = await _seed(db_session)

    events = await _drain_turn(db_session, student, sid)

    assert events, "stream produced no events"
    _assert_no_stub(events)

    # The interviewer turn equals the deterministic static fallback question.
    row = await repo.get_session(db_session, session_id=sid, user_id=student.user_id)
    assert row is not None
    expected = prompts.fallback_next_turn(row.grounding_json or {})
    done = events[-1]
    assert done["type"] == "done"
    assert done["text"] == expected

    turns = await repo.load_turns(db_session, session_id=sid)
    interviewer_lines = [t.text for t in turns if t.speaker == SPEAKER_INTERVIEWER]
    assert interviewer_lines[-1] == expected
    for line in interviewer_lines:
        assert "[offline]" not in (line or "")


async def test_stream_interviewer_defensively_drops_offline_stub_when_live(
    db_session, monkeypatch
) -> None:
    """Defensive first-chunk guard (pure unit test on ``stream_interviewer``).

    Force ``real_provider_active`` True yet make the runner yield the ``[offline]``
    stub token-by-token (as ``OfflineProvider.stream`` does). The guard must drop
    the whole turn and yield the static fallback instead — never the scaffold.
    Patching the runner's ``stream`` keeps this off the metered DB commit path.
    """

    from app.ai.gateway import factory
    from app.ai.gateway.task_runner import AiTaskRunner

    grounding = {"locale": "vi", "job": {"title": "Backend Intern"}}
    stub = prompts_offline_stub()

    async def _fake_stream(self, messages, *, temperature=0.2, max_tokens=1024):
        # Mirror OfflineProvider.stream: one whitespace-delimited word per chunk.
        words = stub.split(" ")
        for i, word in enumerate(words):
            yield word if i == len(words) - 1 else word + " "

    monkeypatch.setattr(factory, "real_provider_active", lambda: True)
    monkeypatch.setattr(AiTaskRunner, "stream", _fake_stream)

    chunks = [
        c
        async for c in conversation_service.stream_interviewer(
            db_session,
            user_id=uuid.uuid4(),
            grounding=grounding,
            turns=[],
            target_questions=5,
        )
    ]

    joined = "".join(chunks)
    assert "[offline]" not in joined, f"leaked offline scaffold: {joined!r}"
    assert "kiểm thử" not in joined
    assert joined == prompts.fallback_next_turn(grounding)


def prompts_offline_stub() -> str:
    """The exact OfflineProvider stub shape (marker + scaffold + echo)."""

    return (
        "[offline] Đây là phản hồi mô phỏng để kiểm thử. (ref:abc123def456) "
        "Yêu cầu: Let's begin the interview."
    )


def test_is_offline_stub_detects_marker() -> None:
    """The shared detector recognises the OfflineProvider scaffold prefix."""

    assert conversation_service.is_offline_stub("[offline] Đây là phản hồi mô phỏng.")
    assert not conversation_service.is_offline_stub("Cảm ơn bạn. Hãy kể về một dự án.")
    assert not conversation_service.is_offline_stub(None)

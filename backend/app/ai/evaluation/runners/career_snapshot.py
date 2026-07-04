"""Eval runner + checker for the ``career_snapshot`` family.

Exercises the REAL ``profile_service.get_ai_career_snapshot`` use case
(student-facing, read-only advisory summary of job-search activity per
``docs/AI_PRODUCT_SPEC.md`` §3) end to end, including the permission check
and the deterministic fallback message (which is built directly from
``app_counts`` when the AI call fails, never from the model). DB-touching
helpers are mocked at their boundary — ``_shared.load_owned_profile`` and
the cross-module recruitment reads (``count_student_applications``,
``list_upcoming_student_interviews``) — while ``generate_note`` is patched
at its source module (``app.ai.cv.llm``) because ``profile_service`` imports
both the LLM call and the recruitment reads lazily inside the function body,
so a source-module patch is what those lazy imports actually resolve to at
call time.

Note: like the other runners in this package, ``generate_note`` is mocked
wholesale here rather than only its provider boundary, so the real
``guard_completion`` scrubbing inside ``app.ai.cv.llm`` does not run in this
gate — that scrubbing has its own dedicated coverage in
``tests/unit/test_output_guard.py``. Leakage-key assertions below therefore
validate the surrounding shaping/fallback code path (fixture text is chosen
to be leak-free), not the guard itself.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evaluation.models import Probe
from app.modules.student_profiles.application import profile_service as svc
from app.shared.permissions import Principal

# The DB boundary (``_shared.load_owned_profile`` and the recruitment reads
# below) is fully mocked, so no real query ever reaches this session — the
# cast documents that this stand-in is never dereferenced, rather than
# widening the real service's signature to accept ``None``.
_NULL_SESSION = cast(AsyncSession, None)

_STUDENT = Principal(
    user_id=uuid.uuid4(),
    persona="student",
    permissions=frozenset({"profile:read"}),
)


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    llm_note = inp.get("llm_note")
    provider_down = inp.get("provider") == "unavailable"
    total = int(inp.get("total_applications", 0))
    active = int(inp.get("active_applications", 0))
    upcoming_count = int(inp.get("interviews_upcoming", 0))

    profile = SimpleNamespace(
        is_open_to_work=inp.get("open_to_work", True),
        headline=inp.get("headline", ""),
    )

    async def _fake_load_owned_profile(*_a: Any, **_k: Any) -> Any:
        return profile

    async def _fake_count_student_applications(*_a: Any, **_k: Any) -> dict:
        return {"total": total, "active": active}

    async def _fake_list_upcoming(*_a: Any, **_k: Any) -> list[Any]:
        return [object()] * upcoming_count

    async def _fake_generate_note(**_kwargs: Any) -> str:
        if provider_down:
            raise RuntimeError("provider unavailable (eval fallback case)")
        if llm_note is None:
            raise RuntimeError("no llm_note stub provided")
        return llm_note

    with (
        mock.patch.object(svc._shared, "load_owned_profile", new=_fake_load_owned_profile),
        mock.patch(
            "app.modules.recruitment.application.dashboard_read.count_student_applications",
            new=_fake_count_student_applications,
        ),
        mock.patch(
            "app.modules.recruitment.application.dashboard_read.list_upcoming_student_interviews",
            new=_fake_list_upcoming,
        ),
        mock.patch("app.ai.cv.llm.generate_note", new=_fake_generate_note),
    ):
        try:
            result = await svc.get_ai_career_snapshot(_NULL_SESSION, principal=_STUDENT)
        except Exception as exc:  # defensive — should never happen offline
            return Probe(kind="career_snapshot", raised_message=str(exc))

    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="career_snapshot", blob=blob, data={"result": result})


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``career_snapshot`` probes."""
    result = (probe.data or {}).get("result") or {}
    if key == "no_crash":
        return None
    if key == "is_fallback":
        got = bool(result.get("is_fallback"))
        return None if got == bool(exp) else f"is_fallback expected {exp}, got {got}"
    if key == "snapshot_nonempty":
        got = bool((result.get("snapshot") or "").strip())
        return None if got == bool(exp) else f"snapshot_nonempty expected {exp}, got {got}"
    if key == "snapshot_contains":
        return None if str(exp).lower() in (result.get("snapshot") or "").lower() else (
            f"snapshot should contain {exp!r}"
        )
    if key == "blob_excludes":
        return None if str(exp).lower() not in probe.blob else f"result should exclude {exp!r}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"result should contain {exp!r}"
    return None  # unknown / informational key

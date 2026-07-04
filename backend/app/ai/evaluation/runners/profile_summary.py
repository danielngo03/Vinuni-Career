"""Eval runner + checker for the ``profile_summary`` family.

Exercises the REAL ``profile_service.get_ai_summary_draft`` use case
end-to-end (student-facing, read-only advisory), including the permission
check and the static-template fallback. DB-touching helpers are mocked at
their boundary (``_shared.load_owned_profile``, ``loaders.load_skills``/
``load_experience``, ``user_service.get_user_by_id``); ``generate_note`` is
patched at its source module (``app.ai.cv.llm``) because ``profile_service``
imports it lazily inside the function body.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evaluation.models import Probe
from app.modules.student_profiles.application import profile_service as svc
from app.shared.permissions import Principal

# The DB boundary (``_shared.load_owned_profile``, ``loaders.load_skills``/
# ``load_experience``, ``user_service.get_by_id``) is fully mocked below, so
# no real query ever reaches this session — the cast documents that this
# stand-in is never dereferenced, rather than widening the real service's
# signature to accept ``None``.
_NULL_SESSION = cast(AsyncSession, None)

_STUDENT = Principal(
    user_id=uuid.uuid4(),
    persona="student",
    permissions=frozenset({"profile:read"}),
)


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    ai_text = inp.get("ai_text")
    provider_down = inp.get("provider") == "unavailable"

    profile = SimpleNamespace(
        id=uuid.uuid4(),
        major=inp.get("major", ""),
        degree_level=inp.get("degree_level", ""),
        headline=inp.get("headline", ""),
    )
    skills = [SimpleNamespace(name=n) for n in (inp.get("skills") or [])]
    experiences = [SimpleNamespace(title=t) for t in (inp.get("experience_titles") or [])]
    user_obj = SimpleNamespace(full_name=inp.get("name", ""))

    async def _fake_load_owned_profile(*_a: Any, **_k: Any) -> Any:
        return profile

    async def _fake_load_skills(*_a: Any, **_k: Any) -> list[Any]:
        return skills

    async def _fake_load_experience(*_a: Any, **_k: Any) -> list[Any]:
        return experiences

    async def _fake_get_by_id(*_a: Any, **_k: Any) -> Any:
        return user_obj

    async def _fake_generate_note(**_kwargs: Any) -> str:
        if provider_down:
            raise RuntimeError("provider unavailable (eval fallback case)")
        return ai_text if ai_text is not None else "A generated summary draft."

    with (
        mock.patch.object(svc._shared, "load_owned_profile", new=_fake_load_owned_profile),
        mock.patch.object(svc.loaders, "load_skills", new=_fake_load_skills),
        mock.patch.object(svc.loaders, "load_experience", new=_fake_load_experience),
        mock.patch.object(svc.user_service, "get_by_id", new=_fake_get_by_id),
        mock.patch("app.ai.cv.llm.generate_note", new=_fake_generate_note),
    ):
        try:
            result = await svc.get_ai_summary_draft(_NULL_SESSION, principal=_STUDENT)
        except Exception as exc:  # defensive — should never happen offline
            return Probe(kind="profile_summary", raised_message=str(exc))

    blob = (result.get("draft") or "").lower()
    return Probe(kind="profile_summary", blob=blob, data={"result": result})


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``profile_summary`` probes."""
    result = (probe.data or {}).get("result") or {}
    if key == "no_crash":
        return None
    if key == "is_fallback":
        got = bool(result.get("is_fallback"))
        return None if got == bool(exp) else f"is_fallback expected {exp}, got {got}"
    if key == "draft_contains":
        return None if str(exp).lower() in probe.blob else f"draft should contain {exp!r}"
    if key == "draft_excludes":
        return None if str(exp).lower() not in probe.blob else f"draft should exclude {exp!r}"
    return None  # unknown / informational key

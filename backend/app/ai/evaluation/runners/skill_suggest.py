"""Eval runner + checker for the ``skill_suggest`` family.

Exercises the REAL ``profile_service.get_ai_skill_suggestions`` use case
(student-facing, read-only advisory per ``docs/AI_PRODUCT_SPEC.md`` §3) end
to end, including the permission check and the post-LLM filtering logic
(dedup against existing skills, cap at 8, curated fallback on any AI
failure). DB-touching helpers are mocked at their boundary — ``_shared.
load_owned_profile`` and ``loaders.load_skills``/``load_experience`` — while
``generate_json_note`` is patched at its source module
(``app.ai.cv.llm``) because ``profile_service`` imports it lazily inside the
function body, so the source patch is what the lazy import actually resolves
to at call time.
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

# The DB boundary (``_shared.load_owned_profile``, ``loaders.load_skills``/
# ``load_experience``) is fully mocked below, so no real query ever reaches
# this session — the cast documents that this stand-in is never dereferenced,
# rather than widening the real service's signature to accept ``None``.
_NULL_SESSION = cast(AsyncSession, None)

_STUDENT = Principal(
    user_id=uuid.uuid4(),
    persona="student",
    permissions=frozenset({"profile:read"}),
)


def _fake_profile(inp: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        major=inp.get("major", ""),
        headline=inp.get("headline", ""),
    )


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    llm_json = inp.get("llm_json")
    provider_down = inp.get("provider") == "unavailable"
    existing_skills = [
        SimpleNamespace(name=n) for n in (inp.get("existing_skills") or [])
    ]
    experiences = [
        SimpleNamespace(title=t) for t in (inp.get("experience_titles") or [])
    ]
    profile = _fake_profile(inp)

    async def _fake_load_owned_profile(*_a: Any, **_k: Any) -> Any:
        return profile

    async def _fake_load_skills(*_a: Any, **_k: Any) -> list[Any]:
        return existing_skills

    async def _fake_load_experience(*_a: Any, **_k: Any) -> list[Any]:
        return experiences

    async def _fake_generate_json_note(**_kwargs: Any) -> dict:
        if provider_down:
            raise RuntimeError("provider unavailable (eval fallback case)")
        return llm_json or {}

    with (
        mock.patch.object(svc._shared, "load_owned_profile", new=_fake_load_owned_profile),
        mock.patch.object(svc.loaders, "load_skills", new=_fake_load_skills),
        mock.patch.object(svc.loaders, "load_experience", new=_fake_load_experience),
        mock.patch("app.ai.cv.llm.generate_json_note", new=_fake_generate_json_note),
    ):
        try:
            result = await svc.get_ai_skill_suggestions(_NULL_SESSION, principal=_STUDENT)
        except Exception as exc:  # defensive — should never happen offline
            return Probe(kind="skill_suggest", raised_message=str(exc))

    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="skill_suggest", blob=blob, data={"result": result})


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``skill_suggest`` probes."""
    result = (probe.data or {}).get("result") or {}
    if key == "no_crash":
        return None
    if key == "is_fallback":
        got: Any = bool(result.get("is_fallback"))
        return None if got == bool(exp) else f"is_fallback expected {exp}, got {got}"
    if key == "suggestion_count_at_most":
        n = len(result.get("suggestions") or [])
        return None if n <= int(exp) else f"suggestion count {n} exceeds cap {exp}"
    if key == "suggestion_count_at_least":
        n = len(result.get("suggestions") or [])
        return None if n >= int(exp) else f"suggestion count {n} below minimum {exp}"
    if key == "excludes_existing_skill":
        existing_lower = str(exp).lower()
        suggested_lower = [s.lower() for s in (result.get("suggestions") or [])]
        return None if existing_lower not in suggested_lower else (
            f"suggestions should not repeat existing skill {exp!r}"
        )
    if key == "all_suggestions_are_strings":
        for s in result.get("suggestions") or []:
            if not isinstance(s, str):
                return f"malformed suggestion entry leaked: {s!r}"
        return None
    if key == "blob_excludes":
        return None if str(exp).lower() not in probe.blob else f"result should exclude {exp!r}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"result should contain {exp!r}"
    return None  # unknown / informational key

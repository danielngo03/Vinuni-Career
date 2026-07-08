"""Persona registry shape — the single seam that maps persona → chat behaviour (B1).

Locks the architecture contract: one ``PersonaProfile`` per persona
(prompt + planner + tool_persona), a student/alumni/partner/university row each,
byte-identical student & partner prompts, a university seam whose planner defers
to the LLM loop, and an unknown-persona fallback to the safe student default.
Adding a 4th persona is a SINGLE registry edit.
"""

from __future__ import annotations

import uuid

from app.ai.prompts.assistant import v1 as assistant_prompt
from app.ai.prompts.assistant_partner import v1 as partner_prompt
from app.ai.prompts.assistant_university import v1 as university_prompt
from app.modules.ai_assistant.application.agentic import planner
from app.modules.ai_assistant.application.agentic.persona_registry import (
    PERSONA_REGISTRY,
    resolve_persona_profile,
)
from app.modules.ai_assistant.application.chat_service import _system_prompt_for
from app.modules.ai_assistant.application.tools.specs import (
    PARTNER_USER,
    STUDENT,
    UNIVERSITY_STAFF,
)
from app.shared import personas
from app.shared.permissions import Principal

# --------------------------------------------------------------------------- #
# B1 — persona registry shape                                                 #
# --------------------------------------------------------------------------- #


def test_registry_covers_every_real_persona() -> None:
    assert set(PERSONA_REGISTRY) == {
        personas.STUDENT,
        personas.ALUMNI,
        personas.PARTNER_MEMBER,
        personas.UNIVERSITY_STAFF,
    }


def test_student_and_partner_prompts_are_byte_identical_to_before() -> None:
    # Behaviour preservation: the registry must return the SAME prompt objects
    # the old scattered branching returned.
    assert (
        resolve_persona_profile(personas.STUDENT).system_prompt
        is assistant_prompt.SYSTEM_PROMPT
    )
    assert (
        resolve_persona_profile(personas.ALUMNI).system_prompt
        is assistant_prompt.SYSTEM_PROMPT
    )
    assert (
        resolve_persona_profile(personas.PARTNER_MEMBER).system_prompt
        is partner_prompt.PARTNER_SYSTEM_PROMPT
    )


def test_university_profile_is_a_correct_seam_not_the_student_stub() -> None:
    profile = resolve_persona_profile(personas.UNIVERSITY_STAFF)
    # A real, distinct university prompt (no longer the student prompt).
    assert profile.system_prompt is university_prompt.UNIVERSITY_SYSTEM_PROMPT
    assert profile.system_prompt is not assistant_prompt.SYSTEM_PROMPT
    # Its planner is the university adapter (defers to the LLM loop).
    assert profile.planner is planner.university_agent_plan
    # Its tool surface maps to the university tool persona — and never advertises
    # a student-only or partner-only tool.
    assert profile.tool_persona == UNIVERSITY_STAFF
    tools = profile.tool_specs()
    assert tools  # non-empty shared surface
    assert "search_jobs" not in tools  # student-only
    assert "get_partner_pipeline_summary" not in tools  # partner-only
    assert "knowledge_base_query" in tools  # shared


def test_persona_profiles_map_to_correct_tool_persona() -> None:
    assert resolve_persona_profile(personas.STUDENT).tool_persona == STUDENT
    assert resolve_persona_profile(personas.ALUMNI).tool_persona == STUDENT
    assert resolve_persona_profile(personas.PARTNER_MEMBER).tool_persona == PARTNER_USER


def test_unknown_persona_falls_back_to_student_default() -> None:
    fallback = resolve_persona_profile("some_future_persona")
    assert fallback.tool_persona == STUDENT
    assert fallback.system_prompt is assistant_prompt.SYSTEM_PROMPT
    # None (defensive) resolves too.
    assert resolve_persona_profile(None).tool_persona == STUDENT


def test_system_prompt_for_uses_the_registry() -> None:
    uni = Principal(user_id=uuid.uuid4(), persona=personas.UNIVERSITY_STAFF)
    partner = Principal(user_id=uuid.uuid4(), persona=personas.PARTNER_MEMBER)
    student = Principal(user_id=uuid.uuid4(), persona=personas.STUDENT)
    assert _system_prompt_for(uni) is university_prompt.UNIVERSITY_SYSTEM_PROMPT
    assert _system_prompt_for(partner) is partner_prompt.PARTNER_SYSTEM_PROMPT
    assert _system_prompt_for(student) is assistant_prompt.SYSTEM_PROMPT

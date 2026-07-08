"""Persona registry — the single seam that maps a persona to its chat behaviour.

Historically the assistant branched on ``principal.persona`` in THREE scattered
places (system-prompt selection in ``chat_service``, planner routing in
``planner.build_agent_plan``, and the tool-persona map in ``tools.dispatch``),
so adding a persona meant editing all three and was easy to get wrong (the
university persona was a half-wired stub as a result).

This module replaces the prompt + planner branching with ONE data structure: a
``PersonaProfile`` per persona holding

- ``system_prompt``  — the persona's LLM system prompt,
- ``planner``        — the deterministic pre-LLM planner for that persona,
- ``tool_persona``   — the ``ToolSpec.persona`` vocabulary the persona maps to,
- ``tool_specs()``   — the tool surface advertised/allowed for the persona.

Adding a 4th persona is now a SINGLE registry entry (plus its prompt + planner),
not a hunt across the codebase. ``tools.dispatch`` keeps its own defensive
persona→tool-persona map (it must not import this agentic module — that would
create a prompt/tool import cycle); both derive their persona strings from
``app.shared.personas`` so they cannot drift.

The planner functions live in ``planner`` (they need its private recent-entity
resolver); this module imports them at load time. ``planner.build_agent_plan``
imports ``resolve_persona_profile`` lazily to avoid a circular import.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.ai.prompts.assistant import v1 as assistant_prompt
from app.ai.prompts.assistant_partner import v1 as partner_prompt
from app.ai.prompts.assistant_university import v1 as university_prompt
from app.modules.ai_assistant.application.agentic import planner
from app.modules.ai_assistant.application.agentic.models import AgentPlan
from app.modules.ai_assistant.application.tool_registry import TOOL_SPECS, ToolSpec
from app.modules.ai_assistant.application.tools.specs import (
    PARTNER_USER,
    STUDENT,
    UNIVERSITY_STAFF,
)
from app.shared import personas

# A per-persona deterministic planner. Signature matches ``build_agent_plan`` so
# a profile's planner is a drop-in for the per-turn call. Returning ``None`` sends
# the turn to the governed LLM tool-calling loop (with this persona's prompt).
PersonaPlanner = Callable[..., Awaitable["AgentPlan | None"]]


@dataclass(frozen=True, slots=True)
class PersonaProfile:
    """Everything the chat turn needs to behave correctly for one persona."""

    key: str  # the ``Principal.persona`` string this profile serves
    system_prompt: str  # LLM system prompt for the persona
    planner: PersonaPlanner  # deterministic pre-LLM planner (None → LLM loop)
    tool_persona: str  # the ``ToolSpec.persona`` vocabulary this persona maps to

    def tool_specs(self) -> dict[str, ToolSpec]:
        """Tool specs this persona may see/dispatch (persona-scoped + shared).

        Mirrors the per-prompt ``_*_TOOL_SPECS`` filters and the dispatch persona
        gate: a spec is in-scope when its ``persona`` list contains this
        persona's ``tool_persona``.
        """
        return {
            name: spec
            for name, spec in TOOL_SPECS.items()
            if self.tool_persona in spec.persona
        }


# --------------------------------------------------------------------------- #
# Registry                                                                     #
#                                                                             #
# Adding a persona = add ONE entry here + its prompt module + its planner.     #
# --------------------------------------------------------------------------- #

PERSONA_REGISTRY: dict[str, PersonaProfile] = {
    personas.STUDENT: PersonaProfile(
        key=personas.STUDENT,
        system_prompt=assistant_prompt.SYSTEM_PROMPT,
        planner=planner.student_agent_plan,
        tool_persona=STUDENT,
    ),
    # Alumni reuse the student surface (prompt, planner, and tools) exactly.
    personas.ALUMNI: PersonaProfile(
        key=personas.ALUMNI,
        system_prompt=assistant_prompt.SYSTEM_PROMPT,
        planner=planner.student_agent_plan,
        tool_persona=STUDENT,
    ),
    personas.PARTNER_MEMBER: PersonaProfile(
        key=personas.PARTNER_MEMBER,
        system_prompt=partner_prompt.PARTNER_SYSTEM_PROMPT,
        planner=planner.partner_agent_plan,
        tool_persona=PARTNER_USER,
    ),
    personas.UNIVERSITY_STAFF: PersonaProfile(
        key=personas.UNIVERSITY_STAFF,
        system_prompt=university_prompt.UNIVERSITY_SYSTEM_PROMPT,
        planner=planner.university_agent_plan,
        tool_persona=UNIVERSITY_STAFF,
    ),
}

# Fallback for any persona not in the registry (e.g. an unexpected/guest string
# that somehow reaches an authenticated chat turn). The student profile is the
# safe, least-privileged default: student prompt + student planner + student
# tools, all of which the dispatch persona gate independently re-checks.
_DEFAULT_PROFILE = PERSONA_REGISTRY[personas.STUDENT]


def resolve_persona_profile(persona: str | None) -> PersonaProfile:
    """Resolve the :class:`PersonaProfile` for ``persona`` (never raises).

    Unknown personas fall back to the student profile so a misconfigured or new
    persona degrades to the safe default surface rather than crashing a turn.
    """
    if persona is None:
        return _DEFAULT_PROFILE
    return PERSONA_REGISTRY.get(persona, _DEFAULT_PROFILE)

"""Task H (WS-11 + WS-15 slice) — assistant v2 smart-apply driver prompt.

Offline (no real-model calls). Asserts:

- student sessions select the v2 prompt; partner/university keep their existing
  prompt (persona-branched selection, §8.1);
- the v2 prompt actively drives the smart-apply chain while keeping the
  confirmation protocol intact (every write is a PROPOSAL the student confirms,
  never presented as already-executed; the CV edit is never auto-applied);
- the v2 prompt only advertises STUDENT tools (isolation preserved from v1);
- the v2 prompt leaks no provider/model/token internals (§15);
- v2 is a NEW version — v1 is untouched (rollback substrate, §17);
- §8.2 static-prefix-before-dynamic: the static instruction block precedes the
  registry-derived tool list.
"""

from __future__ import annotations

import uuid

from app.ai.evaluation.leak_checks import FORBIDDEN_TERMS
from app.ai.prompts.assistant import v1 as assistant_v1
from app.ai.prompts.assistant import v2 as assistant_v2
from app.ai.prompts.assistant_partner import v1 as partner_v1
from app.modules.ai_assistant.application import chat_service
from app.modules.ai_assistant.application.tools.specs import STUDENT, TOOL_SPECS
from app.shared.permissions import Principal


def _principal(persona: str) -> Principal:
    return Principal(user_id=uuid.uuid4(), persona=persona)


# --------------------------------------------------------------------------- #
# Persona-branched selection (§8.1)                                            #
# --------------------------------------------------------------------------- #


def test_student_sessions_select_v2_prompt() -> None:
    selected = chat_service._system_prompt_for(_principal("student"))
    assert selected == assistant_v2.STUDENT_SYSTEM_PROMPT
    assert selected != assistant_v1.SYSTEM_PROMPT, "student must move off v1"


def test_partner_sessions_keep_partner_prompt() -> None:
    selected = chat_service._system_prompt_for(_principal("partner_member"))
    assert selected == partner_v1.PARTNER_SYSTEM_PROMPT


def test_university_and_other_personas_keep_v1_prompt() -> None:
    """Non-student, non-partner personas stay on the existing v1 prompt.

    v2's smart-apply chain is student-specific, so university staff (and any
    other future persona) must not silently inherit it.
    """
    for persona in ("university_staff", "alumni", "guest"):
        selected = chat_service._system_prompt_for(_principal(persona))
        assert selected == assistant_v1.SYSTEM_PROMPT, persona


def test_v2_version_stamp_is_distinct_and_v1_untouched() -> None:
    assert assistant_v2.PROMPT_VERSION == "assistant:v2"
    assert assistant_v1.PROMPT_VERSION == "assistant:v1"
    # v1 remains the rollback target — its prompt text is a different object.
    assert assistant_v2.SYSTEM_PROMPT != assistant_v1.SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# Smart-apply chain + confirmation protocol (§4.3)                             #
# --------------------------------------------------------------------------- #


def test_v2_drives_the_full_smart_apply_chain() -> None:
    prompt = assistant_v2.SYSTEM_PROMPT.lower()
    # The four loop-closing steps are named as tools the assistant proposes.
    for tool in (
        "get_skill_gap",
        "tailor_cv_to_job",
        "draft_and_attach_cover_letter",
        "apply_job",
    ):
        assert tool in prompt, f"v2 must reference {tool} in the smart-apply chain"
    assert "smart apply" in prompt


def test_v2_preserves_confirmation_protocol_and_no_auto_execution() -> None:
    prompt = assistant_v2.SYSTEM_PROMPT.lower()
    # Confirmation protocol wording: propose-not-execute + never-claim-done.
    assert "confirmation" in prompt
    assert "never state or imply" in prompt
    # The model may only PROPOSE writes; it does not execute them.
    assert "propose" in prompt
    # Advisory / student-has-final-say language present.
    assert "advisory only" in prompt


def test_v2_never_auto_applies_cv_edits() -> None:
    prompt = assistant_v2.SYSTEM_PROMPT.lower()
    assert "pending" in prompt and "never auto-applied" in prompt
    # It must not instruct the model to directly edit/publish a CV.
    assert "auto-applied" in prompt


# --------------------------------------------------------------------------- #
# Isolation + leakage (v1 guarantees preserved)                               #
# --------------------------------------------------------------------------- #


def test_v2_advertises_only_student_tools() -> None:
    for name, spec in assistant_v2._STUDENT_TOOL_SPECS.items():
        assert STUDENT in spec.persona, name
    # Known partner-only tools never appear in the student v2 prompt.
    for partner_tool in (
        "move_candidate_stage",
        "search_partner_candidates",
        "get_partner_jobs",
        "suggest_scorecard",
    ):
        assert partner_tool not in assistant_v2.SYSTEM_PROMPT


def test_v2_write_tools_are_all_confirmation_required() -> None:
    """Every write tool v2 is allowed to propose is confirmation-gated in the registry."""
    assert assistant_v2._STUDENT_WRITE_TOOLS, "v2 must know its write tools"
    for name in assistant_v2._STUDENT_WRITE_TOOLS:
        assert TOOL_SPECS[name].permission_class == "confirmation_required"
    # The loop-closing writes are covered.
    for name in ("tailor_cv_to_job", "draft_and_attach_cover_letter", "apply_job"):
        assert name in assistant_v2._STUDENT_WRITE_TOOLS


def test_v2_prompt_has_no_provider_or_model_leakage() -> None:
    blob = assistant_v2.SYSTEM_PROMPT.lower()
    for term in FORBIDDEN_TERMS:
        assert term not in blob, f"v2 prompt leaked forbidden term {term!r}"


# --------------------------------------------------------------------------- #
# §8.2 static-prefix-before-dynamic                                           #
# --------------------------------------------------------------------------- #


def test_v2_static_prefix_precedes_dynamic_tool_list() -> None:
    prompt = assistant_v2.SYSTEM_PROMPT
    tools_header = prompt.index("## Available tools")
    # The static instruction sections all appear before the dynamic tool list.
    for header in (
        "## Scope boundary",
        "## Smart apply",
        "## Confirmation protocol",
        "## Safety and RBAC",
    ):
        assert prompt.index(header) < tools_header, f"{header} must precede the tool list"

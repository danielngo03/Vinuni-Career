"""Gap -> CV-Studio "apply this improvement" hand-off (pure, deterministic).

Closes the loop between the CV-JD fit gaps and the CV Studio pending-diff editor.
For each fit gap this builds a well-formed, confirmation-gated hand-off that the
EXISTING natural-language CV edit flow can consume directly:

    POST /api/v1/cvs/{cv_id}/ai-edit-command  (body: {"instruction": "..."})
        -> ``cv_ai_service.request_edit_command`` -> ``CvAiSuggestion`` (pending)
        -> student accepts -> new ``cv_versions`` row (audited)

This module ONLY builds the request shape (the entrypoint + a grounded, advisory
instruction). It is intentionally pure (stdlib only, no DB, no model call) so it
can be shared by the ``documents`` fit-explanation path and the ``opportunities``
student-intelligence path without an import cycle.

Safety guarantees (``docs/CV_STUDIO_SPEC.md`` "Natural-Language AI Editing",
``.claude/rules/ai.md``):

- NEVER mutates a CV and NEVER invents a qualification. The instruction is
  explicitly CONDITIONAL ("only if you genuinely have experience"), and the
  downstream edit-command runs the fabrication check and returns a PENDING diff
  the student must confirm (``requires_confirmation``).
- Advisory only: the hand-off is a suggestion the student may trigger; nothing is
  applied automatically.
- Leak-safe: carries only the target CV id, the gap skill, localized advisory
  copy, and the ready-to-send request body. No provider/model/token/score/
  confidence internals.
"""

from __future__ import annotations

# The CV-Studio natural-language edit endpoint the hand-off feeds into.
HANDOFF_ACTION = "cv_edit_command"
_ENDPOINT_TEMPLATE = "/api/v1/cvs/{cv_id}/ai-edit-command"

# English-authored default instructions (user-facing output language is chosen by
# ``locale``; prompt/guardrail text elsewhere stays English per the AI rules).
_INSTRUCTION: dict[str, str] = {
    "vi": (
        'Bổ sung bằng chứng cụ thể cho kỹ năng "{skill}" vào phần kinh nghiệm '
        "hoặc dự án của tôi — chỉ khi tôi thực sự có kinh nghiệm với kỹ năng này."
    ),
    "en": (
        'Add concrete evidence for the "{skill}" skill to my experience or '
        "projects section — only if I genuinely have experience with it."
    ),
}


def build_improvement(
    *,
    cv_id: str | None,
    skill: str,
    locale: str = "vi",
    suggestion: str | None = None,
) -> dict | None:
    """Return the hand-off payload for one gap, or ``None`` when unusable.

    ``None`` when there is no target CV to improve (``cv_id`` falsy) or the gap
    skill is blank — the frontend simply omits the "apply this improvement" entry
    in that case. ``suggestion`` (optional) is advisory rationale copy shown next
    to the button; it never asserts the student HAS the skill.
    """

    skill = (skill or "").strip()
    if not cv_id or not skill:
        return None
    template = _INSTRUCTION.get(locale) or _INSTRUCTION["en"]
    rationale = (suggestion or "").strip() or None
    return {
        "action": HANDOFF_ACTION,
        "method": "POST",
        "endpoint": _ENDPOINT_TEMPLATE.format(cv_id=cv_id),
        "cv_id": cv_id,
        "skill": skill,
        "rationale": rationale,
        # Ready-to-send body for POST /cvs/{cv_id}/ai-edit-command. The frontend
        # attaches its own idempotency_key before sending.
        "request": {"instruction": template.format(skill=skill)},
        # The downstream edit-command ALWAYS returns a pending diff requiring
        # explicit student confirmation, then creates a new version on accept.
        "requires_confirmation": True,
    }


def build_improvements(
    *,
    cv_id: str | None,
    gaps: list[str],
    locale: str = "vi",
    limit: int = 5,
) -> list[dict]:
    """Build hand-offs for up to ``limit`` gaps (blank/duplicate-safe)."""

    out: list[dict] = []
    seen: set[str] = set()
    for raw in gaps or []:
        skill = str(raw or "").strip()
        key = skill.lower()
        if not skill or key in seen:
            continue
        seen.add(key)
        handoff = build_improvement(cv_id=cv_id, skill=skill, locale=locale)
        if handoff is not None:
            out.append(handoff)
        if len(out) >= limit:
            break
    return out

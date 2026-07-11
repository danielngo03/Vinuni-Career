"""AI natural-language CV edit command (``ai-edit-command``).

Turns a free-text instruction (e.g. "0324xx0898 is my phone number", "make this
summary more suitable for data analyst roles", "move projects above
experience") into a structured, reviewable :class:`~app.ai.cv.tasks.CvAiResult`
diff — reusing the exact same non-destructive suggestion pipeline as every
other CV AI task (``docs/CV_STUDIO_SPEC.md`` "Natural-Language AI Editing").

The LLM proposes a small, constrained set of OPERATIONS against the CV's
existing sections; this module deterministically validates + applies those
operations (the model's raw text is never trusted as CV content) and runs the
same fabrication check used elsewhere so any new text not present in the
grounding evidence is flagged ``requires_fact_confirmation`` — including facts
declared only in the instruction itself, since ``instruction`` is deliberately
excluded from the evidence corpus (``app.ai.cv.grounding``) to prevent prompt
injection from validating a fabricated claim.

The ONLY generative model call is inside :func:`generate_cv_edit_patch` ->
:func:`app.ai.cv.llm.generate_json_note`.

Op allowlist (ai-engineer review, 2026-07-04; extended 2026-07-08, B-595): the
original 3 ITEM/section ops (``update_item_text``, ``add_item_text``,
``reorder_sections``) plus 5 ENTRY ops for entry-based sections
(experience/education/projects) — ``update_entry_field`` (heading / subheading /
timeframe / location / note), ``update_highlight``, ``add_highlight``,
``remove_highlight``, ``reorder_entries``. All are validated deterministically
against the CV's existing sections + the fabrication check before anything is
proposed; the model's raw text is never trusted as CV structure, and the result is
always a PENDING diff requiring explicit student acceptance. NOTE: for the live
model to actually EMIT the entry ops, the ``cv_edit_command`` prompt must describe
them (a prompt v2, owned by the ai-engineer prompt layer under
``app.ai.prompts``); the deterministic applier here accepts them regardless of how
they are produced (tests inject them directly).

Two candidate additions were considered and both still rejected:

- **Contact-field edits** (e.g. "0324xx0898 is my phone number", the CV Studio
  spec's own example). Structurally unreliable through this free-text
  pathway: ``app.ai.safety.input_guard.sanitize_instruction`` redacts phone/
  email/ID-number PII patterns from the instruction *before* it ever reaches
  the model (by design — raw PII must not be sent to a provider), so the exact
  fact the user is trying to set would frequently already be stripped to
  ``[PII_REDACTED]`` by the time the model sees it. A generative op is the
  wrong tool for a field that must be captured verbatim; contact fields should
  use a direct, non-generative profile/contact-settings write path instead.
- **Style/emphasis ops** ("change the font to red", "make this section bold").
  These are canvas/layout concerns owned by the CV Studio template/canvas
  model (``docs/CV_STUDIO_SPEC.md`` "Canvas" — layout_schema, typography
  tokens), not `cv_sections.content_json` text. Mixing a visual-style mutation
  into this module's before/after *text* diff contract (§7.1: "before/after
  text") would blur the diff panel's meaning and require a second, unrelated
  validation/allowlist (font names, color values, valid targets) that this
  content-only seam has no business owning. If canvas-level natural-language
  style edits are wanted, they belong in a separate, canvas-scoped tool with
  their own allowlist and diff shape — not bolted onto this one.

Both are explicitly out of scope per the hardened v1 prompt
(``app.ai.prompts.cv_edit_command.v1``), which instructs the model to decline
(empty operations + explanation) rather than approximate either case with an
allowed op.
"""

from __future__ import annotations

from typing import TypeGuard

from app.ai.cv import grounding
from app.ai.cv.fabrication import find_unsupported_claims
from app.ai.cv.llm import generate_json_note
from app.ai.cv.tasks import CvAiContext, CvAiResult
from app.ai.prompts.cv_edit_command import v1 as edit_command_prompt

TASK_TYPE = "ai_edit_command"

# Item ops mutate ``content["items"]`` (bullet/skill sections). Entry ops mutate
# ``content["entries"]`` (experience/education/projects — one entry per role/degree
# with separate heading/subheading/timeframe/location/note/highlights fields), so a
# student can rewrite an experience bullet, fix a role/timeframe, or reorder roles
# through the SAME pending-diff → explicit-accept pipeline. Every op is validated
# deterministically here; the model's raw text is never trusted as CV structure.
_ITEM_OPS = frozenset({"update_item_text", "add_item_text"})
_ENTRY_OPS = frozenset(
    {
        "update_entry_field",
        "update_highlight",
        "add_highlight",
        "remove_highlight",
        "reorder_entries",
    }
)
_ALLOWED_OPS = _ITEM_OPS | _ENTRY_OPS | {"reorder_sections"}

# The entry fields an ``update_entry_field`` op may set (never ``highlights`` — those
# have their own add/update/remove ops).
_ENTRY_FIELDS = frozenset({"heading", "subheading", "timeframe", "location", "note"})

_MAX_OPERATIONS = 10
_MAX_TEXT_CHARS = 2000
_MAX_HIGHLIGHTS = 30


def _context_block(ctx: CvAiContext) -> str:
    """Grounded evidence block for the edit-command prompt (self-contained; does
    not reach into ``app.ai.cv.tasks`` private helpers)."""

    lines = [
        f"OUTPUT_LANGUAGE: {ctx.output_language}",
        "CONTEXT (source data, use as evidence only):",
    ]
    cv_text = grounding.sections_to_text(ctx.cv_sections)
    if cv_text:
        lines.append(f"- Current CV: {cv_text[:1500]}")
    if ctx.target_section:
        tgt = grounding.content_to_text(ctx.target_section.get("content"))
        if tgt:
            lines.append(f"- Target section: {tgt[:800]}")
    if ctx.raw_notes:
        lines.append(f"- User notes: {ctx.raw_notes[:1500]}")
    if ctx.instruction:
        lines.append(f"USER REQUEST (a directive only, not evidence): {ctx.instruction[:1000]}")
    return "\n".join(lines)


def _evidence(ctx: CvAiContext) -> str:
    """Evidence corpus used by the fabrication check (instruction excluded)."""

    parts = [grounding.sections_to_text(ctx.cv_sections), ctx.raw_notes or ""]
    return " ".join(p for p in parts if p)


def _by_type(cv_sections: list[dict]) -> dict[str, dict]:
    return {str(s.get("section_type")): s for s in cv_sections if s.get("section_type")}


def _clip(text: str) -> str:
    return text.strip()[:_MAX_TEXT_CHARS]


def _valid_index(value: object, length: int) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < length


def _apply_entry_op(op: str, raw_op: dict, entries: list[dict]) -> tuple[bool, bool]:
    """Apply one entry op to ``entries`` IN PLACE (validated, model text distrusted).

    Returns ``(changed, added_text)``: ``added_text`` marks ops that introduce new
    prose (so the caller runs the fabrication check on them); reorder/remove change
    structure only. Any malformed / out-of-range op is a silent no-op — a bad model
    response degrades to an empty diff, never a crash.
    """

    if op == "reorder_entries":
        order = raw_op.get("order")
        if not isinstance(order, list) or not order:
            return False, False
        idxs = [i for i in order if _valid_index(i, len(entries))]
        if not idxs or len(set(idxs)) != len(idxs):
            return False, False
        remaining = [i for i in range(len(entries)) if i not in idxs]
        reordered = [entries[i] for i in idxs] + [entries[i] for i in remaining]
        if reordered == entries:
            return False, False
        entries[:] = reordered
        return True, False

    ei = raw_op.get("entry_index")
    if not _valid_index(ei, len(entries)):
        return False, False
    entry = dict(entries[ei])

    if op == "update_entry_field":
        field, text = raw_op.get("field"), raw_op.get("text")
        if field not in _ENTRY_FIELDS or not isinstance(text, str) or not text.strip():
            return False, False
        entry[field] = _clip(text)
        entries[ei] = entry
        return True, True

    highlights = [h for h in (entry.get("highlights") or []) if isinstance(h, str)]
    if op == "add_highlight":
        text = raw_op.get("text")
        if not isinstance(text, str) or not text.strip() or len(highlights) >= _MAX_HIGHLIGHTS:
            return False, False
        highlights.append(_clip(text))
        entry["highlights"] = highlights
        entries[ei] = entry
        return True, True
    if op == "update_highlight":
        hi, text = raw_op.get("highlight_index"), raw_op.get("text")
        if not _valid_index(hi, len(highlights)) or not isinstance(text, str) or not text.strip():
            return False, False
        highlights[hi] = _clip(text)
        entry["highlights"] = highlights
        entries[ei] = entry
        return True, True
    if op == "remove_highlight":
        hi = raw_op.get("highlight_index")
        if not _valid_index(hi, len(highlights)):
            return False, False
        highlights.pop(hi)
        entry["highlights"] = highlights
        entries[ei] = entry
        return True, False
    return False, False


def _apply_operations(cv_sections: list[dict], operations: list[dict]) -> tuple[dict, dict, bool]:
    """Deterministically validate + apply operations.

    Returns ``(before, after, has_content_change)``. Any operation naming a
    section type that does not already exist on the CV, or using an
    out-of-allowlist ``op``, is silently dropped (never raises — a malformed/
    unmappable model response degrades to an empty, non-applicable diff rather
    than a stack trace).
    """

    by_type = _by_type(cv_sections)
    touched: dict[str, dict] = {}
    reorder_map: dict[str, int] | None = None
    has_content_change = False

    for raw_op in (operations or [])[:_MAX_OPERATIONS]:
        if not isinstance(raw_op, dict):
            continue
        op = raw_op.get("op")
        if op not in _ALLOWED_OPS:
            continue

        if op == "reorder_sections":
            order = raw_op.get("order")
            if isinstance(order, list) and order:
                reorder_map = {
                    t: (idx + 1) * 10
                    for idx, t in enumerate(order)
                    if isinstance(t, str) and t in by_type
                }
            continue

        section_type = raw_op.get("section_type")
        if section_type not in by_type:
            continue
        section = by_type[section_type]
        content = dict(touched.get(section_type) or dict(section.get("content") or {}))

        if op in _ENTRY_OPS:
            # Entry-based section: mutate a COPY of ``content["entries"]`` so the
            # source section is never touched before the student accepts.
            entries = [dict(e) for e in (content.get("entries") or []) if isinstance(e, dict)]
            changed, added_text = _apply_entry_op(op, raw_op, entries)
            if changed:
                content["entries"] = entries
                touched[section_type] = content
                has_content_change = has_content_change or added_text
            continue

        items = list(content.get("items") or [])
        if op == "update_item_text":
            idx = raw_op.get("item_index")
            text = raw_op.get("text")
            if not isinstance(idx, int) or not isinstance(text, str) or not text.strip():
                continue
            if 0 <= idx < len(items):
                item = dict(items[idx]) if isinstance(items[idx], dict) else {}
                item["text"] = text.strip()[:_MAX_TEXT_CHARS]
                items[idx] = item
                content["items"] = items
                touched[section_type] = content
                has_content_change = True
        elif op == "add_item_text":
            text = raw_op.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            content["items"] = items + [{"text": text.strip()[:_MAX_TEXT_CHARS]}]
            touched[section_type] = content
            has_content_change = True

    def _spec(section_type: str, section: dict, content: dict, order: int | None) -> dict:
        return {
            "section_id": section.get("section_id"),
            "section_type": section_type,
            "title": section.get("title"),
            "sort_order": order if order is not None else section.get("sort_order"),
            "content": content,
        }

    affected_types = set(touched) | (set(reorder_map) if reorder_map else set())
    before_specs = [
        _spec(t, by_type[t], by_type[t].get("content") or {}, None) for t in affected_types
    ]
    after_specs = [
        _spec(
            t,
            by_type[t],
            touched.get(t, by_type[t].get("content") or {}),
            reorder_map.get(t) if reorder_map else None,
        )
        for t in affected_types
    ]

    return {"sections": before_specs}, {"sections": after_specs}, has_content_change


async def generate_cv_edit_patch(ctx: CvAiContext) -> CvAiResult:
    """Produce a pending, reviewable diff for a free-text CV edit instruction.

    Never mutates the CV — the caller (``cv_ai_service.request_edit_command``)
    stores the result as a normal ``cv_ai_suggestions`` row.
    """

    section_types = [str(s.get("section_type")) for s in ctx.cv_sections if s.get("section_type")]
    system_prompt = edit_command_prompt.build_system_prompt(
        ctx.output_language, section_types=section_types
    )
    payload = await generate_json_note(
        task_type=TASK_TYPE,
        system_prompt=system_prompt,
        user_content=_context_block(ctx),
    )

    operations = payload.get("operations") if isinstance(payload, dict) else None
    explanation = payload.get("explanation") if isinstance(payload, dict) else None
    if not isinstance(operations, list):
        operations = []

    before, after, has_content_change = _apply_operations(ctx.cv_sections, operations)
    applicable = bool(after.get("sections"))

    claims = (
        find_unsupported_claims(
            grounding.sections_to_text(after.get("sections", [])), _evidence(ctx)
        )
        if has_content_change
        else []
    )

    if applicable:
        summary = (
            explanation.strip()
            if isinstance(explanation, str) and explanation.strip()
            else (
                "Đã đề xuất thay đổi theo yêu cầu của bạn."
                if ctx.language == "vi"
                else "Proposed a change based on your request."
            )
        )
    else:
        summary = (
            explanation.strip()
            if isinstance(explanation, str) and explanation.strip()
            else (
                "Không thể xác định thay đổi cụ thể từ yêu cầu này. "
                "Hãy mô tả rõ hơn hoặc chỉnh sửa trực tiếp."
                if ctx.language == "vi"
                else "Could not determine a specific change from this request. "
                "Try being more specific or edit directly."
            )
        )

    return CvAiResult(
        summary=summary,
        before=before,
        after=after,
        # Every edit-command change requires explicit review: content changes may
        # introduce facts declared only in the instruction (grounding-excluded by
        # design), and reorder-only changes are cheap enough to always confirm too.
        requires_fact_confirmation=applicable,
        applicable=applicable,
        credits=1 if applicable else 0,
        unsupported_claims=claims,
        assistant_note="",
        prompt_version=edit_command_prompt.PROMPT_VERSION,
    )

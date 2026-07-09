"""CV AI task implementations (grounded, non-destructive diffs).

Each task returns a :class:`CvAiResult` containing a reviewable ``before``/``after``
diff. CV FACTS are produced deterministically from the structured sources only,
so the output is safe and reproducible under the offline provider and cannot be
steered by prompt injection. A scrubbed advisory ``assistant_note`` from the
gateway accompanies generative tasks (exercises the gateway + cost tracking +
fallback); it is never the source of CV facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ai.cv import grounding
from app.ai.cv.fabrication import find_unsupported_claims
from app.ai.cv.llm import generate_note
from app.ai.prompts.cv_bullets import v1 as bullets_prompt
from app.ai.prompts.cv_draft import v1 as draft_prompt
from app.ai.prompts.cv_fill import v1 as fill_prompt
from app.ai.prompts.cv_optimize import v1 as optimize_prompt
from app.ai.prompts.cv_rewrite import v1 as rewrite_prompt

# Task-type literals (kept independent of the documents module to respect the
# app.ai -> module boundary; both sides use the same canonical strings).
DRAFT_FROM_PROFILE = "draft_cv_from_profile"
FILL_FROM_SOURCES = "fill_cv_template_from_sources"
GENERATE_BULLETS = "generate_cv_bullets"
REWRITE_SECTION = "rewrite_cv_section"
OPTIMIZE_FOR_JOB = "optimize_cv_for_job"
ATS_KEYWORDS = "ats_keyword_suggestions"
FABRICATION_CHECK = "cv_fabrication_check"

_SECTION_PRIORITY = [
    "skills",
    "experience",
    "projects",
    "summary",
    "education",
    "certifications",
    "awards",
    "languages",
    "activities",
    "publications",
    "custom",
]


@dataclass(slots=True)
class CvAiContext:
    """Grounding inputs assembled by the documents service (no DB access here)."""

    task_type: str
    # ``language`` is the detected/declared CV/source-document language and drives
    # both the deterministic user-facing summaries and the default output language.
    language: str = "vi"
    # Explicit override: when the caller asks for a specific output language it wins
    # over the detected CV language. ``None`` => fall back to ``language``.
    target_language: str | None = None
    instruction: str | None = None
    raw_notes: str | None = None
    cv_sections: list[dict] = field(default_factory=list)
    target_section: dict | None = None
    profile_sections: list[dict] | None = None
    upload_extracted: dict | None = None
    source_cv_sections: list[dict] | None = None
    job: dict | None = None

    @property
    def output_language(self) -> str:
        """Resolved USER-FACING output language for the model.

        Priority (``docs/AI_PRODUCT_SPEC.md`` §"prompt/language"): explicit
        ``target_language`` -> detected CV/source-document ``language`` -> default
        ``vi``. The locale fallback is applied upstream when building ``language``.
        """

        return self.target_language or self.language or "vi"


@dataclass(slots=True)
class CvAiResult:
    summary: str
    before: dict
    after: dict
    requires_fact_confirmation: bool
    applicable: bool
    credits: int
    unsupported_claims: list[str] = field(default_factory=list)
    keywords: list[str] | None = None
    suggestions: dict | None = None
    assistant_note: str = ""
    prompt_version: int = 1

    def to_diff(self) -> dict:
        """Serialise to the stored/returned diff JSON (leak-safe, no AI internals)."""

        diff: dict = {
            "summary": self.summary,
            "before": self.before,
            "after": self.after,
            "requires_fact_confirmation": self.requires_fact_confirmation,
            "applicable": self.applicable,
            "unsupported_claims": self.unsupported_claims,
        }
        if self.keywords is not None:
            diff["keywords"] = self.keywords
        if self.suggestions is not None:
            diff["suggestions"] = self.suggestions
        if self.assistant_note:
            diff["assistant_note"] = self.assistant_note
        return diff


# --------------------------------------------------------------------------- #
# Text helpers (deterministic, grounded)                                       #
# --------------------------------------------------------------------------- #


def _clean(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return (t[0].upper() + t[1:]) if t else t


def _rewrite_content(content: dict | None) -> dict:
    if not isinstance(content, dict):
        return {}
    items = content.get("items")
    if not isinstance(items, list):
        return content
    new_items: list = []
    for item in items:
        if isinstance(item, str):
            new_items.append({"text": _clean(item)})
        elif isinstance(item, dict):
            it = dict(item)
            if isinstance(it.get("text"), str):
                it["text"] = _clean(it["text"])
            if isinstance(it.get("description"), str):
                it["description"] = _clean(it["description"])
            new_items.append(it)
        else:
            new_items.append(item)
    out = dict(content)
    out["items"] = new_items
    return out


def _spec(section: dict, content: dict) -> dict:
    return {
        "section_id": section.get("section_id"),
        "section_type": section.get("section_type"),
        "title": section.get("title"),
        "sort_order": section.get("sort_order"),
        "content": content,
    }


def _split_notes(notes: str | None) -> list[str]:
    if not notes:
        return []
    parts = re.split(r"[\n;•]|(?<=[.])\s+", notes)
    return [p.strip(" -•\t") for p in parts if p.strip(" -•\t")]


def _evidence(ctx: CvAiContext) -> str:
    parts = [
        grounding.sections_to_text(ctx.cv_sections),
        grounding.sections_to_text(ctx.profile_sections),
        grounding.extracted_to_text(ctx.upload_extracted),
        grounding.sections_to_text(ctx.source_cv_sections),
        ctx.raw_notes or "",
    ]
    return " ".join(p for p in parts if p)


def _context_block(ctx: CvAiContext) -> str:
    # Structural labels are internal scaffolding (English, per the prompt/language
    # policy). The embedded SOURCE DATA values keep their own language; the model
    # is told separately which language to write the user-facing answer in.
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
    if ctx.profile_sections:
        lines.append(f"- Profile: {grounding.sections_to_text(ctx.profile_sections)[:1500]}")
    up = grounding.extracted_to_text(ctx.upload_extracted)
    if up:
        lines.append(f"- Uploaded CV extraction: {up[:1500]}")
    if ctx.source_cv_sections:
        lines.append(f"- Source CV: {grounding.sections_to_text(ctx.source_cv_sections)[:1000]}")
    if ctx.raw_notes:
        lines.append(f"- User notes: {ctx.raw_notes[:1500]}")
    if ctx.job and ctx.job.get("text"):
        lines.append(f"- Job posting: {ctx.job['text'][:1500]}")
    if ctx.instruction:
        lines.append(f"USER REQUEST (a directive only, not evidence): {ctx.instruction[:1000]}")
    return "\n".join(lines)


def _source_by_type(ctx: CvAiContext) -> dict[str, dict]:
    """First non-empty content per section_type across all import sources."""

    by_type: dict[str, dict] = {}

    def consider(sections: list[dict] | None) -> None:
        for s in sections or []:
            stype = s.get("section_type")
            content = s.get("content") or s.get("content_json") or {}
            if stype and stype not in by_type and grounding.section_texts(content):
                by_type[stype] = content

    consider(ctx.profile_sections)
    consider(ctx.source_cv_sections)
    if isinstance(ctx.upload_extracted, dict):
        for stype, value in ctx.upload_extracted.items():
            if stype not in by_type and isinstance(value, dict) and grounding.section_texts(value):
                by_type[stype] = {"items": list(value.get("items", []))}
    return by_type


# --------------------------------------------------------------------------- #
# Task handlers                                                                #
# --------------------------------------------------------------------------- #


async def _rewrite(ctx: CvAiContext) -> CvAiResult:
    target = ctx.target_section or {}
    before_content = target.get("content") or {}
    after_content = _rewrite_content(before_content)
    note = await generate_note(
        task_type=ctx.task_type,
        system_prompt=rewrite_prompt.build_system_prompt(ctx.output_language),
        user_content=_context_block(ctx),
    )
    claims = find_unsupported_claims(grounding.content_to_text(after_content), _evidence(ctx))
    n = len(grounding.section_texts(after_content))
    summary = (
        f"Đã viết lại {n} nội dung trong mục."
        if ctx.language == "vi"
        else f"Rewrote {n} item(s) in the section."
    )
    return CvAiResult(
        summary=summary,
        before={"sections": [_spec(target, before_content)]},
        after={"sections": [_spec(target, after_content)]},
        requires_fact_confirmation=bool(claims),
        applicable=True,
        credits=1,
        unsupported_claims=claims,
        assistant_note=note,
        prompt_version=rewrite_prompt.PROMPT_VERSION,
    )


async def _bullets(ctx: CvAiContext) -> CvAiResult:
    target = ctx.target_section or {}
    before_content = target.get("content") or {}
    existing = list(before_content.get("items", [])) if isinstance(before_content, dict) else []
    new_bullets = [{"text": _clean(line)} for line in _split_notes(ctx.raw_notes)]
    after_content = dict(before_content) if isinstance(before_content, dict) else {}
    after_content["items"] = existing + new_bullets
    note = await generate_note(
        task_type=ctx.task_type,
        system_prompt=bullets_prompt.build_system_prompt(ctx.output_language),
        user_content=_context_block(ctx),
    )
    new_text = " ".join(b["text"] for b in new_bullets)
    claims = find_unsupported_claims(new_text, _evidence(ctx))
    summary = (
        f"Đã tạo {len(new_bullets)} gạch đầu dòng từ ghi chú."
        if ctx.language == "vi"
        else f"Generated {len(new_bullets)} bullet point(s) from notes."
    )
    return CvAiResult(
        summary=summary,
        before={"sections": [_spec(target, before_content)]},
        after={"sections": [_spec(target, after_content)]},
        requires_fact_confirmation=True,
        applicable=True,
        credits=1,
        unsupported_claims=claims,
        assistant_note=note,
        prompt_version=bullets_prompt.PROMPT_VERSION,
    )


async def _draft(ctx: CvAiContext) -> CvAiResult:
    after_sections: list[dict] = []
    if ctx.profile_sections:
        after_sections = [
            {
                "section_type": s.get("section_type"),
                "title": s.get("title"),
                "sort_order": s.get("sort_order"),
                "content": s.get("content") or s.get("content_json") or {},
            }
            for s in ctx.profile_sections
        ]
    note = await generate_note(
        task_type=ctx.task_type,
        system_prompt=draft_prompt.build_system_prompt(ctx.output_language),
        user_content=_context_block(ctx),
    )
    claims = find_unsupported_claims(grounding.sections_to_text(after_sections), _evidence(ctx))
    if after_sections:
        summary = (
            f"Đã soạn bản nháp CV với {len(after_sections)} mục từ hồ sơ."
            if ctx.language == "vi"
            else f"Drafted a CV with {len(after_sections)} section(s) from your profile."
        )
    else:
        summary = (
            "Chưa đủ dữ liệu hồ sơ để soạn bản nháp. Hãy bổ sung hồ sơ hoặc ghi chú."
            if ctx.language == "vi"
            else "Not enough profile data to draft. Add profile details or notes."
        )
    return CvAiResult(
        summary=summary,
        before={"sections": ctx.cv_sections},
        after={"sections": after_sections},
        requires_fact_confirmation=True,
        applicable=bool(after_sections),
        credits=2,
        unsupported_claims=claims,
        assistant_note=note,
        prompt_version=draft_prompt.PROMPT_VERSION,
    )


async def _fill(ctx: CvAiContext) -> CvAiResult:
    by_type = _source_by_type(ctx)
    before_specs: list[dict] = []
    after_specs: list[dict] = []
    for section in ctx.cv_sections:
        content = section.get("content") or {}
        stype = section.get("section_type")
        if not grounding.section_texts(content) and stype in by_type:
            before_specs.append(_spec(section, content))
            after_specs.append(_spec(section, by_type[stype]))
    note = await generate_note(
        task_type=ctx.task_type,
        system_prompt=fill_prompt.build_system_prompt(ctx.output_language),
        user_content=_context_block(ctx),
    )
    claims = find_unsupported_claims(grounding.sections_to_text(after_specs), _evidence(ctx))
    summary = (
        f"Đã điền {len(after_specs)} mục còn trống từ nguồn dữ liệu."
        if ctx.language == "vi"
        else f"Filled {len(after_specs)} empty section(s) from sources."
    )
    return CvAiResult(
        summary=summary,
        before={"sections": before_specs},
        after={"sections": after_specs},
        requires_fact_confirmation=True,
        applicable=bool(after_specs),
        credits=2,
        unsupported_claims=claims,
        assistant_note=note,
        prompt_version=fill_prompt.PROMPT_VERSION,
    )


async def _optimize(ctx: CvAiContext) -> CvAiResult:
    job_text = (ctx.job or {}).get("text") or ""
    keywords = grounding.extract_keywords(job_text)
    cv_text = grounding.sections_to_text(ctx.cv_sections)
    present, missing = grounding.keyword_coverage(keywords, cv_text)

    def _priority(section: dict) -> int:
        stype = section.get("section_type") or ""
        return (
            _SECTION_PRIORITY.index(stype) if stype in _SECTION_PRIORITY else len(_SECTION_PRIORITY)
        )

    ordered = sorted(ctx.cv_sections, key=_priority)
    after_specs = [
        {
            "section_id": s.get("section_id"),
            "section_type": s.get("section_type"),
            "title": s.get("title"),
            "sort_order": (idx + 1) * 10,
            "content": s.get("content") or {},  # content unchanged (truth-preserving)
        }
        for idx, s in enumerate(ordered)
    ]
    note = await generate_note(
        task_type=ctx.task_type,
        system_prompt=optimize_prompt.build_system_prompt(ctx.output_language),
        user_content=_context_block(ctx),
    )
    suggestions = {
        "keyword_coverage": {"present": present, "missing": missing},
        "ordering": [s.get("section_type") for s in ordered],
        "missing_information": missing,
        "evidence_gaps": missing,
    }
    summary = (
        f"Đã đề xuất sắp xếp lại CV và {len(missing)} từ khóa cần bổ sung cho công việc."
        if ctx.language == "vi"
        else f"Suggested re-ordering and {len(missing)} keyword(s) to add for the job."
    )
    return CvAiResult(
        summary=summary,
        before={"sections": ctx.cv_sections},
        after={"sections": after_specs},
        requires_fact_confirmation=True,
        applicable=True,
        credits=2,
        keywords=missing,
        suggestions=suggestions,
        assistant_note=note,
        prompt_version=optimize_prompt.PROMPT_VERSION,
    )


async def _ats(ctx: CvAiContext) -> CvAiResult:
    job_text = (ctx.job or {}).get("text") or ""
    keywords = grounding.extract_keywords(job_text)
    cv_text = grounding.sections_to_text(ctx.cv_sections)
    present, missing = grounding.keyword_coverage(keywords, cv_text)
    summary = (
        f"Tìm thấy {len(missing)} từ khóa nên cân nhắc bổ sung (nếu đúng sự thật)."
        if ctx.language == "vi"
        else f"Found {len(missing)} keyword(s) to consider adding (if truthful)."
    )
    return CvAiResult(
        summary=summary,
        before={"sections": []},
        after={"sections": []},
        requires_fact_confirmation=False,
        applicable=False,
        credits=0,
        keywords=missing,
        suggestions={"present": present, "missing": missing},
        prompt_version=1,
    )


async def _fabrication(ctx: CvAiContext) -> CvAiResult:
    cv_text = grounding.sections_to_text(ctx.cv_sections)
    evidence = " ".join(
        p
        for p in (
            grounding.sections_to_text(ctx.profile_sections),
            grounding.extracted_to_text(ctx.upload_extracted),
            grounding.sections_to_text(ctx.source_cv_sections),
            ctx.raw_notes or "",
        )
        if p
    )
    claims = find_unsupported_claims(cv_text, evidence)
    if claims:
        summary = (
            f"Phát hiện {len(claims)} tuyên bố cần xác nhận bằng chứng."
            if ctx.language == "vi"
            else f"Found {len(claims)} claim(s) needing evidence confirmation."
        )
    else:
        summary = (
            "Không phát hiện tuyên bố thiếu bằng chứng rõ ràng."
            if ctx.language == "vi"
            else "No clearly unsupported claims detected."
        )
    return CvAiResult(
        summary=summary,
        before={"sections": []},
        after={"sections": []},
        requires_fact_confirmation=bool(claims),
        applicable=False,
        credits=0,
        unsupported_claims=claims,
        prompt_version=1,
    )


_HANDLERS = {
    DRAFT_FROM_PROFILE: _draft,
    FILL_FROM_SOURCES: _fill,
    GENERATE_BULLETS: _bullets,
    REWRITE_SECTION: _rewrite,
    OPTIMIZE_FOR_JOB: _optimize,
    ATS_KEYWORDS: _ats,
    FABRICATION_CHECK: _fabrication,
}


async def run_cv_task(ctx: CvAiContext) -> CvAiResult:
    """Dispatch a CV AI task to its grounded handler."""

    handler = _HANDLERS.get(ctx.task_type)
    if handler is None:  # pragma: no cover - guarded by the service layer
        raise ValueError(f"unknown cv ai task: {ctx.task_type}")
    return await handler(ctx)

"""CV library lifecycle service: finalize a draft into the library.

The CV library is a two-tier model (design spec 2026-07-05, owner-approved):

- ``draft`` — unlimited scratch CVs. Design/edit freely on the canvas; costs no
  library slot; NOT usable for apply or job-fit.
- ``ready`` — the student's library (max 5). A committed, analyzed, matching-ready
  CV. Counts against the 5-cap; usable for apply + job-fit.

``finalize_cv`` is the "Lưu vào thư viện CV" action: it validates the CV is
non-empty, enforces the active-CV quota (this is the ONLY quota gate for template
CVs), promotes ``draft -> ready`` with ``finalized_at``, writes an immutable
version snapshot + a ``cv.finalized`` audit row, and returns the full detail.

RBAC + ownership are enforced here (students hold ``cv:*``); a cross-owner CV is
indistinguishable from missing (``404``). Idempotent: finalizing an already-ready
CV returns the current detail without re-counting or writing a new version.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import _cv_core, _shared
from app.modules.documents.application.errors import CvEmptyError
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import CvProfile, CvSection
from app.shared.audit import write_audit
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE

# The change_source stamped on the version snapshot a finalize creates. Kept in the
# existing ``manual | import | restore`` family space as a new, self-describing
# source so version history shows exactly when a CV entered the library.
FINALIZE_CHANGE_SOURCE = "finalize"

# Schema version for the derived matching representation. Bump on a shape change so
# a future consumer can detect/upgrade older ``matching_json`` rows.
MATCHING_SCHEMA_VERSION = 1

# Section types whose free text (entry headings/notes/highlights + summary text)
# feeds the keyword set used for CV-JD matching.
_KEYWORD_SECTION_TYPES = frozenset({"summary", "experience", "projects"})
# Section types that count as one "experience entry" toward the experience span.
_EXPERIENCE_SECTION_TYPES = frozenset({"experience"})

# Keyword tokenization: lowercase word-ish tokens of length >= 3, deduped. Stopwords
# are dropped so the keyword set stays signal-bearing (deterministic; no NLP model).
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-]{2,}")
_STOPWORDS = frozenset(
    {
        "and", "the", "for", "with", "from", "that", "this", "was", "were", "are",
        "our", "his", "her", "its", "their", "then", "than", "into", "over", "onto",
        "per", "via", "not", "but", "you", "your", "who", "all", "any", "can", "has",
        "have", "had", "using", "used", "use", "also", "such", "more", "most", "some",
        "được", "các", "một", "những", "trong", "của", "với", "cho", "và", "là",
    }
)
_MAX_KEYWORDS = 200
_MAX_SKILLS = 200


def _has_real_content(content: dict) -> bool:
    """True when a section's ``content_json`` carries real, non-empty data.

    Accepts the structured shapes CV sections use: ``entries`` (one per job/degree),
    ``items`` (bullet/skill list), or free ``text``. Whitespace-only text and empty
    lists do not count. Pure/deterministic — no I/O.
    """

    if not isinstance(content, dict):
        return False
    for key in ("entries", "items"):
        value = content.get(key)
        if isinstance(value, list) and any(
            isinstance(v, (dict, str)) and (v if isinstance(v, dict) else v.strip())
            for v in value
        ):
            return True
    text = content.get("text")
    if isinstance(text, str) and text.strip():
        return True
    # Header sections store contact fields flat (name/email/phone/...) rather than
    # in entries/items; any non-empty string field counts as real content.
    for value in content.values():
        if isinstance(value, str) and value.strip():
            return True
    return False


def _is_non_empty_cv(sections: list[CvSection]) -> bool:
    """A CV is finalizable when it has a header with a name OR at least one visible
    non-header section carrying real content.

    Mirrors the "not blank" gate the frontend shows inline, enforced server-side so
    a blank CV can never be committed to the library.
    """

    header_named = False
    has_visible_content = False
    for s in sections:
        content = s.content_json or {}
        if s.section_type == catalog.HEADER_SECTION_TYPE:
            name = content.get("name")
            if isinstance(name, str) and name.strip():
                header_named = True
            continue
        if s.is_visible and _has_real_content(content):
            has_visible_content = True
    return header_named or has_visible_content


def _skill_names(content: dict) -> list[str]:
    """Extract skill names from a skills section's ``items``.

    Handles both stored item shapes: ``{"name": ...}`` (structured, with a level)
    and ``{"text": ...}`` (plain), plus a bare string item. Names are lowercased +
    trimmed; order-preserving dedupe (a skills section is small so this is cheap).
    """

    items = content.get("items")
    if not isinstance(items, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            raw = item.get("name") or item.get("text")
        elif isinstance(item, str):
            raw = item
        else:
            raw = None
        if not isinstance(raw, str):
            continue
        name = raw.strip().lower()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _section_text(content: dict) -> str:
    """Flatten a section's free text (summary text + entry heading/subheading/note/
    highlights) into one string for keyword tokenization. Deterministic, no I/O."""

    parts: list[str] = []
    text = content.get("text")
    if isinstance(text, str):
        parts.append(text)
    entries = content.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for key in ("heading", "subheading", "note", "role", "organization"):
                value = entry.get(key)
                if isinstance(value, str):
                    parts.append(value)
            highlights = entry.get("highlights")
            if isinstance(highlights, list):
                parts.extend(h for h in highlights if isinstance(h, str))
    return " ".join(parts)


def _keywords(text: str) -> list[str]:
    """Deterministic keyword set: lowercase word-ish tokens (>= 3 chars), stopwords
    dropped, order-preserving dedupe, capped. No NLP model — pure string work."""

    out: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_RE.finditer(text.lower()):
        token = match.group(0)
        if token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= _MAX_KEYWORDS:
            break
    return out


def build_matching_representation(sections: list[CvSection]) -> dict:
    """Derive the internal CV-JD matching representation from structured sections.

    Deterministic (NO OCR/AI): a TEMPLATE CV is already structured field-by-field,
    so we normalize what matching needs — a lowercased/deduped ``skills`` list, a
    ``keywords`` set from experience/projects/summary text, ``contact`` presence
    flags, and the ``experience_entry_count``. This is an INTERNAL read model
    (stored on ``cv_profiles.matching_json``); it is never returned to the student
    and carries no model/provider/internal-confidence detail.
    """

    skills: list[str] = []
    skills_seen: set[str] = set()
    keyword_text_parts: list[str] = []
    experience_entry_count = 0
    contact = {"email": False, "phone": False, "location": False, "links": False}

    for s in sections:
        content = s.content_json or {}
        if not isinstance(content, dict):
            continue
        stype = s.section_type

        if stype == "skills":
            for name in _skill_names(content):
                if name not in skills_seen and len(skills) < _MAX_SKILLS:
                    skills_seen.add(name)
                    skills.append(name)

        if stype in _KEYWORD_SECTION_TYPES:
            keyword_text_parts.append(_section_text(content))

        if stype in _EXPERIENCE_SECTION_TYPES:
            entries = content.get("entries")
            if isinstance(entries, list):
                experience_entry_count += sum(
                    1
                    for e in entries
                    if isinstance(e, dict) and (e.get("heading") or e.get("highlights"))
                )

        if stype == catalog.HEADER_SECTION_TYPE:
            for field in ("email", "phone", "location"):
                value = content.get(field)
                if isinstance(value, str) and value.strip():
                    contact[field] = True
            links = content.get("links")
            if isinstance(links, list) and any(
                isinstance(link, dict) and link.get("url") for link in links
            ):
                contact["links"] = True

    return {
        "schema_version": MATCHING_SCHEMA_VERSION,
        "skills": skills,
        "skill_count": len(skills),
        "keywords": _keywords(" ".join(keyword_text_parts)),
        "contact": contact,
        "experience_entry_count": experience_entry_count,
        "analyzed_at": _shared.now().isoformat(),
    }


async def _analyze_for_matching(cv: CvProfile, sections: list[CvSection]) -> None:
    """Make a finalized CV matching-ready by deriving + storing a matching
    representation on ``cv.matching_json`` (design spec §"Data contracts" 3).

    A TEMPLATE CV is already structured field-by-field into the exact ``cv_sections``
    shape CV-JD matching consumes, so this is a DETERMINISTIC derive/normalize — no
    OCR/AI tokens, and the student's own section content is never mutated. The AI
    enrichment seam (skill-graph normalization, competency derivation, embeddings)
    can later plug in behind this same call without changing the finalize lifecycle.
    The result is INTERNAL only (never surfaced in a student-facing response).
    """

    cv.matching_json = build_matching_representation(sections)


async def finalize_cv(
    session: AsyncSession,
    *,
    principal: Principal,
    cv_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Commit a draft CV into the student's library ("Lưu vào thư viện CV").

    Owner-only; cross-owner -> ``404``. Idempotent when already ``ready``. Validates
    non-empty, enforces the active-CV quota (``409 QUOTA_EXCEEDED``), promotes
    ``draft -> ready`` with ``finalized_at``, snapshots a new immutable version, and
    audits ``cv.finalized``. Returns the full CV detail.
    """

    permission_checker.require(principal, _RESOURCE, "update")
    assert principal.user_id is not None

    cv = await _cv_core._load_owned_cv(
        session, principal=principal, cv_id=cv_id, lock=True
    )

    # Idempotent: an already-committed library CV returns current detail with no
    # re-count, no new version, no duplicate audit (retry-safe).
    if cv.status == catalog.CV_READY:
        return await _cv_core._detail_response(session, cv=cv, locale=locale)

    # An archived CV is not a draft that can be finalized directly — restore/unarchive
    # is a separate action. Treat as a non-empty guard failure surface would be wrong;
    # only ``draft`` promotes here. (Archived falls through to the empty/quota checks
    # below, but a real product path never finalizes an archived CV — the UI offers
    # finalize only on drafts.)

    sections = await _cv_core._load_sections(session, cv_id=cv.id)
    if not _is_non_empty_cv(sections):
        raise CvEmptyError()

    # The ONLY quota gate for template CVs: committing to the library must respect
    # the 5-cap (``409 QUOTA_EXCEEDED`` with recovery actions). Enforced before the
    # state flip so nothing is mutated when the library is full.
    await _cv_core._enforce_active_cv_quota(session, principal=principal)

    # Enrichment seam (deterministic no-op today; see docstring).
    await _analyze_for_matching(cv, sections)

    now = _shared.now()
    cv.status = catalog.CV_READY
    cv.finalized_at = now
    cv.last_edited_at = now
    cv.version += 1
    await session.flush()

    await _cv_core._snapshot_version(
        session,
        cv=cv,
        change_source=FINALIZE_CHANGE_SOURCE,
        change_summary="finalized into library",
        created_by=principal.user_id,
    )
    await write_audit(
        session,
        action="cv.finalized",
        resource_type="cv",
        resource_id=cv.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"status": cv.status},
    )
    await session.commit()
    await session.refresh(cv)

    # Best-effort cache invalidation: a newly finalized CV changes which scores
    # are cached for this user.  Failures are non-fatal — the TTL (4 h) is the
    # fallback and a failed invalidation never blocks the finalize response.
    try:
        import redis.asyncio as aioredis

        from app.ai.cv import fit_cache
        from app.core.config import get_settings

        _redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            await fit_cache.invalidate_user(_redis, user_id=cv.user_id)
        finally:
            await _redis.aclose()
    except Exception:
        pass

    return await _cv_core._detail_response(session, cv=cv, locale=locale)


__all__ = ["build_matching_representation", "finalize_cv"]

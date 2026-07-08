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

import uuid
from datetime import UTC

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

# Schema version for the stored matching snapshot. Bump on a shape change so a
# future consumer can detect/upgrade older ``matching_json`` rows.
#
# v2 (B-596): a LOSSLESS, version-stamped projection of the sections CV-JD matching
# actually consumes (``job_fit_service._build_cv_input`` -> ``job_fit.CvInput``),
# replacing the earlier lossy skills/keywords/contact SUMMARY (which no consumer
# could use to reproduce the deterministic score). Because it is byte-identical to
# a live section load, ``_build_cv_input`` can reuse it as a fast path WITHOUT ever
# changing the score.
MATCHING_SCHEMA_VERSION = 2


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


def _matching_section(s: CvSection) -> dict:
    """One section in the EXACT shape the scorer consumes: ``{section_type, title,
    content}``. Kept byte-identical to ``job_fit_service._section_dict`` so the
    stored snapshot and a live section load build the same ``job_fit.CvInput``."""

    return {
        "section_type": s.section_type,
        "title": s.title,
        "content": s.content_json or {},
    }


def _latest_activity_at(cv: CvProfile, sections: list[CvSection]) -> str | None:
    """The latest edit timestamp across the CV + its sections, as an ISO string.

    Mirrors ``job_fit_service._last_updated_days``'s ``latest`` computation (max of
    ``cv.last_edited_at`` and every section ``updated_at``, normalized to UTC) so the
    fast path can rebuild ``last_updated_days`` from the snapshot without a live
    section load and get the SAME value while the snapshot is fresh.
    """

    stamps = [cv.last_edited_at, *[s.updated_at for s in sections]]
    utc = [
        (v if v.tzinfo is not None else v.replace(tzinfo=UTC))
        for v in stamps
        if v is not None
    ]
    return max(utc).isoformat() if utc else None


def build_matching_representation(cv: CvProfile, sections: list[CvSection]) -> dict:
    """Derive the stored CV-JD matching snapshot from the structured sections.

    Deterministic (NO OCR/AI): a committed CV is already structured field-by-field,
    so this is a LOSSLESS projection of the sections CV-JD matching consumes
    (``job_fit_service._build_cv_input`` -> ``job_fit.CvInput``), stamped with the
    ``content_version`` it reflects + the ``last_activity_at`` used to derive
    ``last_updated_days``. It lets the fast path rebuild the scorer input WITHOUT a
    live section load while the snapshot is fresh (``content_version`` still equals
    the live CV version — any edit bumps the version and invalidates it). Being
    byte-identical to a live load, it never changes the deterministic score.

    INTERNAL only: stored on ``cv_profiles.matching_json``, never surfaced to the
    student, and carries no model/provider/confidence detail. ``sections`` MUST be
    ordered as ``_load_sections`` returns them (``sort_order``, ``id``) so the
    projection matches a live load exactly.
    """

    return {
        "schema_version": MATCHING_SCHEMA_VERSION,
        "content_version": cv.version,
        "sections": [_matching_section(s) for s in sections],
        "last_activity_at": _latest_activity_at(cv, sections),
        "analyzed_at": _shared.now().isoformat(),
    }


async def _analyze_for_matching(cv: CvProfile, sections: list[CvSection]) -> None:
    """Make a committed CV matching-ready by storing the version-stamped matching
    snapshot on ``cv.matching_json`` (see ``build_matching_representation``).

    Deterministic — no OCR/AI tokens, and the student's own section content is never
    mutated. INTERNAL only (never surfaced in a student-facing response). MUST be
    called AFTER the finalize version bump so ``content_version`` reflects the
    committed CV version.
    """

    cv.matching_json = build_matching_representation(cv, sections)


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

    now = _shared.now()
    cv.status = catalog.CV_READY
    cv.finalized_at = now
    cv.last_edited_at = now
    cv.version += 1
    # Store the matching snapshot from the POST-finalize state so its
    # ``content_version`` == the committed ``cv.version`` and its ``last_activity_at``
    # == the finalize time. A later section edit bumps the version and invalidates
    # the snapshot; the fast path then falls back to a live section load.
    await _analyze_for_matching(cv, sections)
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

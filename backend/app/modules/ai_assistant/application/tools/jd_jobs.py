"""Partner JD-to-job tools: draft a job from an uploaded JD, then create it.

Human-in-the-loop, two-step:

1. ``draft_job_from_attachment`` (read_only) — reads a JD file the partner
   uploaded to the chat (PDF/image/DOCX), runs the cost-tiered JD extraction
   cascade, and additionally screens the extracted description for biased/
   discriminatory phrasing. Returns a structured DRAFT — nothing is persisted —
   using the FROZEN ``job_draft`` render artifact from ``jd_builder`` (draft +
   missing_required + warnings + ready) so the frontend renders every JD tool
   the same way.
2. ``create_job`` (confirmation_required) — creates the job as a DRAFT posting
   (moderation pending) only after the recruiter confirms. Never auto-publishes.
   Accepts the full ``DRAFT_FIELDS`` set — every field maps 1:1 onto
   ``job_write_service.create_job``'s validated column set.

Both are org-scoped to ``principal.org_id`` and RBAC-gated in the service layer
(``jobs:create`` / ``ai_recruiting:draft_jd``). No provider/model/token internals
are ever surfaced.
"""

from __future__ import annotations

import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_assistant.application.tools import jd_builder
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

# Canonical field tuple + pure coercion helpers live in jd_builder (shared by
# every JD tool); re-exported here for backward-compatible imports/tests.
_DRAFT_FIELDS = jd_builder.DRAFT_FIELDS
_as_skill_list = jd_builder._as_skill_list
_as_int = jd_builder._as_int


def _parse_uuid(raw: str | None) -> _uuid.UUID | None:
    if not raw:
        return None
    try:
        return _uuid.UUID(str(raw).strip())
    except ValueError:
        return None


async def draft_job_from_attachment(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Extract a structured job DRAFT from an uploaded JD file (never persists)."""
    from app.modules.ai_assistant.application import attachment_service
    from app.modules.opportunities.application import jd_upload_service

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}
    attachment_id = _parse_uuid(args.get("attachment_id"))
    if attachment_id is None:
        return {"ok": False, "error": "attachment_id_required"}

    try:
        filename, data = await attachment_service.get_owned_file(
            session, principal=principal, attachment_id=attachment_id
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except AuthRequiredError:
        return {"ok": False, "error": "auth_required"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    try:
        jd = await jd_upload_service.extract_jd_from_upload(filename, data)
    except ValidationFailedError:
        # blank / not-a-JD / corrupt — user-safe, never fabricated into a job.
        return {"ok": False, "error": "not_a_jd"}
    except Exception:
        return {"ok": False, "error": "extract_failed"}

    if jd.get("status") == "ai_unavailable":
        return {"ok": False, "error": "ai_unavailable"}

    draft = jd_builder.normalize_draft_fields(jd)

    # The shared job_draft payload runs the deterministic validator (which
    # includes the bias scan on the extracted description) and attaches the
    # FROZEN render artifact.
    result = jd_builder.job_draft_result(
        draft,
        note=(
            "Draft extracted from the uploaded JD — nothing saved yet. Review the "
            "fields with the recruiter (fill missing_required conversationally), "
            "then call create_job to create it as a DRAFT (it still needs the "
            "recruiter's review + submission for moderation). If a bias warning "
            "is present, advise fixing the wording first."
        ),
        needs_review=bool(jd.get("needs_review", False)),
    )
    # Backward-compatible convenience flag (pre-artifact consumers/tests).
    result["bias_flagged"] = any(w["code"] == "bias_language" for w in result["warnings"])
    return result


async def create_job(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Create a job posting as a DRAFT (confirmation-gated; never auto-published)."""
    from app.modules.auth.application.context import RequestContext
    from app.modules.opportunities.application import job_write_service
    from app.modules.opportunities.application.errors import InvalidJobFieldError

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    title = (args.get("title") or "").strip()
    description = (args.get("description") or "").strip()
    if not title:
        return {"ok": False, "error": "title_required"}
    if not description:
        return {"ok": False, "error": "description_required"}

    # Full DRAFT_FIELDS mapping (invalid enum values are dropped, not rejected —
    # job_write_service re-validates the final payload as the single source of
    # truth for salary/experience sanity).
    payload: dict = dict(jd_builder.normalize_draft_fields(args))
    payload["title"] = title[:255]
    payload["description"] = description

    # NOT-NULL columns need a safe default when the JD didn't specify them.
    payload.setdefault("employment_type", "full_time")
    payload.setdefault("location_type", "onsite")

    try:
        job = await job_write_service.create_job(
            session,
            principal=principal,
            payload=payload,
            ctx=RequestContext(),
            locale=str(args.get("locale") or "vi"),
        )
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except (InvalidJobFieldError, ValidationFailedError):
        return {"ok": False, "error": "invalid_job_fields"}
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    return {
        "ok": True,
        "job_id": job.get("id"),
        "title": job.get("title"),
        "status": job.get("status_label") or job.get("status"),
        "url": f"/partner/jobs/{job.get('id', '')}",
        "note": (
            "Created as a DRAFT (moderation pending). Review and submit it from the "
            "jobs page — it is not visible to candidates until approved."
        ),
    }

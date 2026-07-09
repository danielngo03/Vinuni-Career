"""Partner JD-to-job tools: draft a job from an uploaded JD, then create it.

Human-in-the-loop, two-step:

1. ``draft_job_from_attachment`` (read_only) — reads a JD file the partner
   uploaded to the chat (PDF/image/DOCX), runs the cost-tiered JD extraction
   cascade, and additionally screens the extracted description for biased/
   discriminatory phrasing. Returns a structured DRAFT — nothing is persisted.
   This is a small multi-step pipeline (extract → bias scan → assemble).
2. ``create_job`` (confirmation_required) — creates the job as a DRAFT posting
   (moderation pending) only after the recruiter confirms. Never auto-publishes.

Both are org-scoped to ``principal.org_id`` and RBAC-gated in the service layer
(``jobs:create`` / ``ai_recruiting:draft_jd``). No provider/model/token internals
are ever surfaced.
"""

from __future__ import annotations

import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.domain import lifecycle
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

# Job fields we lift from the extracted JD / accept from the model.
_DRAFT_FIELDS = (
    "title",
    "description",
    "requirements",
    "benefits",
    "employment_type",
    "location_type",
    "location_city",
    "required_skills",
    "preferred_skills",
    "experience_min_years",
    "experience_max_years",
    "seniority_level",
    "salary_min",
    "salary_max",
    "salary_currency",
)


def _parse_uuid(raw: str | None) -> _uuid.UUID | None:
    if not raw:
        return None
    try:
        return _uuid.UUID(str(raw).strip())
    except ValueError:
        return None


def _as_skill_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()][:30]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()][:30]
    return []


def _as_int(value) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


async def draft_job_from_attachment(
    session: AsyncSession, principal: Principal, args: dict
) -> dict:
    """Extract a structured job DRAFT from an uploaded JD file (never persists)."""
    from app.ai.safety.bias_detection import check_bias
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

    draft = {}
    for k in _DRAFT_FIELDS:
        v = jd.get(k)
        if v in (None, "", [], {}):
            continue
        if k in ("required_skills", "preferred_skills"):
            v = _as_skill_list(v)
            if not v:
                continue
        elif k in ("experience_min_years", "experience_max_years", "salary_min", "salary_max"):
            v = _as_int(v)
            if v is None:
                continue
        elif k == "employment_type" and v not in lifecycle.EMPLOYMENT_TYPES:
            continue
        elif k == "location_type" and v not in lifecycle.LOCATION_TYPES:
            continue
        elif k == "seniority_level" and v not in lifecycle.SENIORITY_LEVELS:
            continue
        draft[k] = v

    # Multi-step: screen the extracted description for biased phrasing before the
    # recruiter builds a posting from it.
    bias_flagged = False
    desc = draft.get("description") or ""
    if desc:
        try:
            bias_flagged = bool(check_bias(desc[:6000]).as_dict().get("flagged", False))
        except Exception:
            bias_flagged = False

    return {
        "ok": True,
        "draft": draft,
        "needs_review": bool(jd.get("needs_review", False)),
        "bias_flagged": bias_flagged,
        "note": (
            "Draft extracted from the uploaded JD — nothing saved yet. Review the "
            "fields with the recruiter, then call create_job to create it as a DRAFT "
            "(it still needs the recruiter's review + submission for moderation). If "
            "bias_flagged is true, advise fixing the wording first."
        ),
    }


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

    payload: dict = {"title": title[:255], "description": description}
    for k in _DRAFT_FIELDS:
        if k in ("title", "description"):
            continue
        v = args.get(k)
        if v in (None, "", [], {}):
            continue
        if k in ("required_skills", "preferred_skills"):
            v = _as_skill_list(v)
            if not v:
                continue
        elif k in ("experience_min_years", "experience_max_years", "salary_min", "salary_max"):
            v = _as_int(v)
            if v is None:
                continue
        elif k == "employment_type" and v not in lifecycle.EMPLOYMENT_TYPES:
            continue
        elif k == "location_type" and v not in lifecycle.LOCATION_TYPES:
            continue
        elif k == "seniority_level" and v not in lifecycle.SENIORITY_LEVELS:
            continue
        payload[k] = v

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

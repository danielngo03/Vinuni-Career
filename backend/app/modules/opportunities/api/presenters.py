"""ORM -> friendly response shapes for jobs.

Two detail views exist:

- :func:`public_job_detail` / :func:`public_job_summary` — what guests and
  non-owners receive. **Never** include moderation notes, moderation status, the
  poster's id, or other internal fields.
- :func:`owner_job_detail` / :func:`owner_job_summary` — what the owning org (and
  university moderators) receive: the full record including lifecycle/moderation
  metadata.

Every enum column is paired with a localized label via ``domain.lifecycle``; the
raw code is kept (clients may branch on it) but always accompanied by a label.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.discovery.domain import taxonomy
from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application.org_reporting_facade import (
    OrgSummary,
    company_block,
)
from app.shared.moderation import queue_age_fields, reason_code_label


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _build_locations(job: Job) -> list[dict]:
    """Return the multi-location list, synthesizing from legacy fields when empty.

    Each item includes province_code (links to provinces.code for map features),
    city (display label or fallback), and country.
    """
    if job.locations:
        return [
            {
                "type": loc.get("type", job.location_type),
                "province_code": loc.get("province_code"),
                "ward_code": loc.get("ward_code"),
                "ward_name": loc.get("ward_name"),
                "city": loc.get("city"),
                "country": loc.get("country", "Vietnam"),
            }
            for loc in job.locations
        ]
    return [{
        "type": job.location_type,
        "province_code": None,
        "ward_code": None,
        "ward_name": None,
        "city": job.location_city,
        "country": job.location_country,
    }]


def _salary(job: Job, *, is_owner: bool = False) -> dict | None:
    """Raw numeric salary block.

    Public callers only ever see this when disclosed. Owner-facing views may
    also see the real numbers when ``salary_mode == "hidden"`` (the partner set
    real figures for internal budget/reporting/export use but chose not to
    disclose them publicly) — this is the concrete distinction between
    ``hidden`` and ``negotiable`` per ``docs/API_CONTRACTS.md``.
    """
    if job.salary_is_disclosed:
        return {
            "min": job.salary_min,
            "max": job.salary_max,
            "currency": job.salary_currency,
        }
    if is_owner and job.salary_mode == "hidden":
        return {
            "min": job.salary_min,
            "max": job.salary_max,
            "currency": job.salary_currency,
        }
    return None


def _format_salary_amount(amount: int, *, currency: str, locale: str) -> str:
    if currency.upper() == "VND":
        millions = amount / 1_000_000
        value = f"{millions:.1f}".rstrip("0").rstrip(".")
        return f"{value} {'triệu' if locale == 'vi' else 'M VND'}"
    return f"{amount:,} {currency}".replace(",", "." if locale == "vi" else ",")


def _salary_display(job: Job, *, locale: str) -> dict:
    """Return semantic salary copy for marketplace UI.

    Prefers the stored ``salary_mode`` (set at create/update time, see
    ``api/schemas.py``) so ``hidden`` (real numbers exist but are not public)
    and ``negotiable`` (no real numbers at all) are distinguishable. Falls back
    to the legacy null-combination inference only when ``salary_mode`` is
    unexpectedly absent (defensive — after the ``0055`` migration backfill,
    every row should have a mode).
    """

    currency = job.salary_currency or "VND"
    min_amount = job.salary_min
    max_amount = job.salary_max
    period = job.salary_period or "monthly"
    gross_net = job.salary_gross_net or "unspecified"

    mode = job.salary_mode
    if mode in ("negotiable", "hidden"):
        return {
            "kind": mode,
            "label": "Thỏa thuận" if locale == "vi" else "Negotiable",
            "min": None,
            "max": None,
            "currency": currency,
            "period": period,
            "gross_net": gross_net,
        }
    if mode in ("fixed", "range", "from", "to") and (
        min_amount is not None or max_amount is not None
    ):
        if mode == "fixed":
            label = _format_salary_amount(min_amount, currency=currency, locale=locale)
        elif mode == "range":
            label = (
                f"{_format_salary_amount(min_amount, currency=currency, locale=locale)}"
                f" - {_format_salary_amount(max_amount, currency=currency, locale=locale)}"
            )
            if currency.upper() == "VND":
                label = label.replace(" triệu - ", " - ").replace(" M VND - ", " - ")
        elif mode == "from":
            amount = _format_salary_amount(min_amount, currency=currency, locale=locale)
            label = f"Từ {amount}" if locale == "vi" else f"From {amount}"
        else:  # "to"
            amount = _format_salary_amount(max_amount, currency=currency, locale=locale)
            label = f"Tới {amount}" if locale == "vi" else f"Up to {amount}"
        return {
            "kind": mode,
            "label": label,
            "min": min_amount,
            "max": max_amount,
            "currency": currency,
            "period": period,
            "gross_net": gross_net,
        }

    # --- Legacy inference fallback (mode missing/unbackfilled) ---
    if not job.salary_is_disclosed or (min_amount is None and max_amount is None):
        return {
            "kind": "negotiable",
            "label": "Thỏa thuận" if locale == "vi" else "Negotiable",
            "min": None,
            "max": None,
            "currency": currency,
            "period": period,
            "gross_net": gross_net,
        }
    if min_amount is not None and max_amount is not None:
        if min_amount == max_amount:
            label = _format_salary_amount(min_amount, currency=currency, locale=locale)
            kind = "fixed"
        else:
            label = (
                f"{_format_salary_amount(min_amount, currency=currency, locale=locale)}"
                f" - {_format_salary_amount(max_amount, currency=currency, locale=locale)}"
            )
            if currency.upper() == "VND":
                label = label.replace(" triệu - ", " - ").replace(" M VND - ", " - ")
            kind = "range"
        return {
            "kind": kind,
            "label": label,
            "min": min_amount,
            "max": max_amount,
            "currency": currency,
            "period": period,
            "gross_net": gross_net,
        }
    if min_amount is not None:
        amount = _format_salary_amount(min_amount, currency=currency, locale=locale)
        return {
            "kind": "from",
            "label": f"Từ {amount}" if locale == "vi" else f"From {amount}",
            "min": min_amount,
            "max": None,
            "currency": currency,
            "period": period,
            "gross_net": gross_net,
        }
    amount = _format_salary_amount(max_amount or 0, currency=currency, locale=locale)
    return {
        "kind": "to",
        "label": f"Tới {amount}" if locale == "vi" else f"Up to {amount}",
        "min": None,
        "max": max_amount,
        "currency": currency,
        "period": period,
        "gross_net": gross_net,
    }


def _experience_display(job: Job, *, locale: str) -> dict:
    """Return semantic experience copy for marketplace UI.

    Prefers the stored ``experience_mode`` (new kind vocabulary:
    ``no_requirement`` | ``fresher`` | ``range`` | ``min`` | ``max``). Falls
    back to the legacy null-combination inference (kinds ``not_required`` |
    ``from`` | ``fixed`` | ``range`` | ``up_to``) only when ``experience_mode``
    is unexpectedly absent (defensive — after the ``0055`` migration backfill,
    every row should have a mode).

    ``0`` means entry-level/no prior professional experience, while ``None``
    means the partner did not set a bound. This keeps cases such as
    "Không yêu cầu", "Từ 2 năm", and "1-3 năm" distinct.
    """

    min_years = job.experience_min_years
    max_years = job.experience_max_years

    no_required_vi = "Không yêu cầu kinh nghiệm"
    no_required_en = "No experience required"

    mode = job.experience_mode
    if mode == "no_requirement":
        return {
            "kind": "no_requirement",
            "label": no_required_vi if locale == "vi" else no_required_en,
            "min": None,
            "max": None,
        }
    if mode == "fresher":
        label = (
            "Không yêu cầu kinh nghiệm (Fresher)"
            if locale == "vi"
            else "No experience required (Fresher)"
        )
        return {"kind": "fresher", "label": label, "min": 0, "max": 0}
    if mode == "range" and min_years is not None and max_years is not None:
        label = (
            f"{min_years}-{max_years} năm" if locale == "vi" else f"{min_years}-{max_years} years"
        )
        return {"kind": "range", "label": label, "min": min_years, "max": max_years}
    if mode == "min" and min_years is not None:
        label = f"Từ {min_years} năm" if locale == "vi" else f"From {min_years} years"
        return {"kind": "min", "label": label, "min": min_years, "max": None}
    if mode == "max" and max_years is not None:
        label = f"Tới {max_years} năm" if locale == "vi" else f"Up to {max_years} years"
        return {"kind": "max", "label": label, "min": None, "max": max_years}

    # --- Legacy inference fallback (mode missing/unbackfilled) ---
    if min_years is None and max_years is None:
        return {
            "kind": "not_required",
            "label": no_required_vi if locale == "vi" else no_required_en,
            "min": None,
            "max": None,
        }
    if (min_years is None or min_years == 0) and (max_years is None or max_years == 0):
        return {
            "kind": "not_required",
            "label": no_required_vi if locale == "vi" else no_required_en,
            "min": min_years,
            "max": max_years,
        }
    if (min_years is None or min_years == 0) and max_years is not None:
        label = f"Tới {max_years} năm" if locale == "vi" else f"Up to {max_years} years"
        return {"kind": "up_to", "label": label, "min": min_years, "max": max_years}
    if min_years is not None and max_years is not None:
        if min_years == max_years:
            label = (
                f"{min_years} năm"
                if locale == "vi"
                else f"{min_years} year{'s' if min_years != 1 else ''}"
            )
            return {"kind": "fixed", "label": label, "min": min_years, "max": max_years}
        label = (
            f"{min_years}-{max_years} năm"
            if locale == "vi"
            else f"{min_years}-{max_years} years"
        )
        return {"kind": "range", "label": label, "min": min_years, "max": max_years}
    if min_years is not None:
        label = f"Từ {min_years} năm" if locale == "vi" else f"From {min_years} years"
        return {"kind": "from", "label": label, "min": min_years, "max": None}

    label = f"Tới {max_years} năm" if locale == "vi" else f"Up to {max_years} years"
    return {"kind": "up_to", "label": label, "min": None, "max": max_years}


def _common(job: Job, *, locale: str, is_owner: bool = False) -> dict:
    return {
        "id": str(job.id),
        "org_id": str(job.org_id),
        "title": job.title,
        "slug": job.slug,
        "employment_type": job.employment_type,
        "employment_type_label": lifecycle.employment_type_label(
            job.employment_type, locale=locale
        ),
        "industry_id": str(job.industry_id) if job.industry_id else None,
        "location_type": job.location_type,
        "location_type_label": lifecycle.location_type_label(
            job.location_type, locale=locale
        ),
        "location_city": job.location_city,
        "location_country": job.location_country,
        # Multi-location: always a list. When empty, synthesize from legacy fields.
        "locations": _build_locations(job),
        "required_skills": list(job.required_skills or []),
        "salary": _salary(job, is_owner=is_owner),
        "salary_display": _salary_display(job, locale=locale),
        "experience_display": _experience_display(job, locale=locale),
        "is_featured": job.is_featured,
        "is_sponsored": job.is_sponsored,
        "application_deadline": _iso(job.application_deadline),
        "published_at": _iso(job.published_at),
        # BCP-47 language code of the original JD content.
        # Clients use this to decide whether to offer a translation CTA.
        "language_code": getattr(job, "language_code", None) or "en",
        # CV language requirement set by the partner ("any" | "en" | "vi").
        "cv_language_required": getattr(job, "cv_language_required", "any") or "any",
    }


def _detail_body(job: Job, *, locale: str, is_owner: bool = False) -> dict:
    """Detail fields shared by public + owner detail (no embedded company)."""

    data = _common(job, locale=locale, is_owner=is_owner)
    data.update(
        {
            "description": job.description,
            "requirements": job.requirements,
            "benefits": job.benefits,
            "preferred_skills": list(job.preferred_skills or []),
            "experience_min_years": job.experience_min_years,
            "experience_max_years": job.experience_max_years,
            "experience_mode": job.experience_mode,
            "salary_mode": job.salary_mode,
            "salary_period": job.salary_period,
            "salary_gross_net": job.salary_gross_net,
            "degree_required": job.degree_required,
            "seniority_level": job.seniority_level,
            "candidate_requirements": job.candidate_requirements or {},
            "headcount": job.headcount,
            "view_count": job.view_count,
        }
    )
    return data


def _public_discovery_signals(job: Job, *, industry_slug: str | None) -> dict:
    """Coarse, privacy-safe personalization signals for public (guest) surfaces.

    Both are **tokenizable strings, never UUIDs** — guest discovery emits them as
    interest signals that the ranker tokenizes (``taxonomy.tokens_of``) and matches
    against job title/skill tokens:

    - ``role_family``: a deterministic coarse role family from the title (shared
      vocabulary with the ranker's ``role_family_of``), or ``None`` when the title
      matches no known family.
    - ``industry_slug``: the job's industry taxonomy slug (e.g.
      ``"information-technology"``), resolved by the caller from ``industry_id``,
      or ``None`` when the job has no industry.

    These are public-only signals: intentionally absent from owner/moderator
    projections, which already carry the raw ``industry_id`` for internal use.
    """

    return {
        "role_family": taxonomy.role_family_of(job.title),
        "industry_slug": industry_slug,
    }


def public_job_summary(
    job: Job,
    *,
    company: OrgSummary | None = None,
    locale: str = "vi",
    is_saved: bool = False,
    industry_slug: str | None = None,
) -> dict:
    data = _common(job, locale=locale)
    # Marketplace rows always show the employer (``docs/SCREEN_SPECS.md`` §1.1).
    data["company"] = company_block(company)
    data["is_saved"] = is_saved
    data.update(_public_discovery_signals(job, industry_slug=industry_slug))
    return data


def public_job_detail(
    job: Job,
    *,
    company: OrgSummary | None = None,
    locale: str = "vi",
    is_saved: bool = False,
    industry_slug: str | None = None,
) -> dict:
    data = _detail_body(job, locale=locale)
    data["company"] = company_block(company)
    data["is_saved"] = is_saved
    data.update(_public_discovery_signals(job, industry_slug=industry_slug))
    return data


def _owner_fields(job: Job, *, locale: str) -> dict:
    return {
        "posted_by": str(job.posted_by),
        "visibility": job.visibility,
        "status": job.status,
        "status_label": lifecycle.status_label(job.status, locale=locale),
        "moderation_status": job.moderation_status,
        "moderation_status_label": lifecycle.moderation_label(
            job.moderation_status, locale=locale
        ),
        "moderation_note": job.moderation_note,
        "moderation_reason_code": job.moderation_reason_code,
        "moderation_reason_label": reason_code_label(
            job.moderation_reason_code, locale=locale
        ),
        "submitted_at": _iso(job.submitted_at),
        "approved_at": _iso(job.approved_at),
        "closed_at": _iso(job.closed_at),
        "application_count": job.application_count,
        "version": job.version,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
        "claimed_by": str(job.claimed_by) if job.claimed_by else None,
        "claimed_at": _iso(job.claimed_at),
        **queue_age_fields(
            submitted_at=job.submitted_at, due_by=job.due_by, now=datetime.now(tz=UTC)
        ),
    }


def owner_job_summary(job: Job, *, locale: str = "vi") -> dict:
    data = _common(job, locale=locale, is_owner=True)
    data.update(
        {
            "status": job.status,
            "status_label": lifecycle.status_label(job.status, locale=locale),
            "moderation_status": job.moderation_status,
            "moderation_status_label": lifecycle.moderation_label(
                job.moderation_status, locale=locale
            ),
            "moderation_reason_code": job.moderation_reason_code,
            "moderation_reason_label": reason_code_label(
                job.moderation_reason_code, locale=locale
            ),
            "visibility": job.visibility,
            "version": job.version,
            "created_at": _iso(job.created_at),
            "claimed_by": str(job.claimed_by) if job.claimed_by else None,
            "claimed_at": _iso(job.claimed_at),
            **queue_age_fields(
                submitted_at=job.submitted_at,
                due_by=job.due_by,
                now=datetime.now(tz=UTC),
            ),
        }
    )
    return data


def owner_job_detail(job: Job, *, locale: str = "vi") -> dict:
    # Owner projection is intentionally company-block-free (unchanged contract).
    data = _detail_body(job, locale=locale, is_owner=True)
    data.update(_owner_fields(job, locale=locale))
    return data

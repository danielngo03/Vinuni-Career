"""Public (unauthenticated) organization projections for the career marketplace.

These are the **only** org shapes a guest may receive. They expose nothing
beyond the public company identity: never ``status`` of pending/suspended orgs,
``subscription_tier``, ``settings``, RBAC internals, tax/contact data, or raw
storage paths. The directory/detail services guarantee the row is a ``partner``
that is ``active`` and not soft-deleted before these run; university orgs are
never projected here.

``company_block`` is the small embedded employer summary attached to public job
rows (``docs/SCREEN_SPECS.md`` §1.1: every public job card shows its company).
``public_logo_url`` is the single place logo exposure is decided so it cannot
drift between the directory and embedded job cards.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.modules.organization.domain.models import Organization


def public_logo_url(org: Organization) -> str | None:
    """Resolve a public logo URL, or ``None`` — never a raw storage path.

    When ``logo_path`` is set we return the stable public serve route
    (``GET /api/v1/companies/{slug}/logo``), so the directory, company detail,
    marketplace spotlight, and embedded job ``company`` blocks all expose the same
    safe ``logo_url``. The raw storage key is never returned. The serve endpoint
    independently re-checks public listability, so a stale URL for a now-suspended
    org resolves to ``404`` rather than leaking bytes. A ``?v={version}`` cache key
    lets clients/CDN pick up a replaced logo. ``None`` keeps the initials fallback.
    """

    if not org.logo_path:
        return None
    base = get_settings().app_url.rstrip("/")
    return f"{base}/api/v1/companies/{org.slug}/logo?v={org.version}"


def directory_summary(
    org: Organization,
    *,
    active_job_count: int,
    rating: dict | None = None,
) -> dict:
    """Company card shape for the directory list + marketplace spotlight.

    ``rating`` is the compact aggregate from the reviews facade:
    ``{ overall_avg, review_count }`` — or ``None`` when no published reviews.
    Only ``overall_avg`` and ``review_count`` are included in the directory shape
    to keep the payload small; the full breakdown is on the detail page.
    """

    base: dict[str, Any] = {
        "id": str(org.id),
        "slug": org.slug,
        "display_name": org.display_name,
        "logo_url": public_logo_url(org),
        "industry": org.industry,
        "company_size": org.company_size,
        "headquarters_city": org.headquarters_city,
        "is_verified": org.is_verified,
        "trust_level": org.trust_level,
        "active_job_count": active_job_count,
        "rating": None,
    }
    if rating and rating.get("overall_avg") is not None:
        base["rating"] = {
            "overall_avg": rating["overall_avg"],
            "review_count": rating.get("review_count", 0),
        }
    return base


def company_detail(
    org: Organization,
    *,
    active_job_count: int,
    active_jobs: list[dict],
    rating: dict | None = None,
) -> dict:
    """Company profile shape (directory summary + public profile + open roles).

    ``rating`` is the company-review aggregate block from the reviews facade, or
    ``None`` when the org has no published reviews (the UI shows an empty state,
    never a fabricated score).
    """

    data = directory_summary(org, active_job_count=active_job_count)
    data.update(
        {
            "website_url": org.website_url,
            "description": org.description,
            "founded_year": org.founded_year,
            "verified_at": org.verified_at.isoformat() if org.verified_at else None,
            "active_jobs": active_jobs,
            "rating": rating,
        }
    )
    return data


def company_block(org: Organization | None) -> dict | None:
    """Tiny employer block embedded in a public job row; ``None`` if no org."""

    if org is None:
        return None
    return {
        "slug": org.slug,
        "display_name": org.display_name,
        "logo_url": public_logo_url(org),
        "is_verified": org.is_verified,
    }

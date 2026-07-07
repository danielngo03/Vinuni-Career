"""Job posting service — facade over the split job-service modules.

This module used to be a ~1500-line monolith. It has been decomposed (pure
move + re-export, no behaviour change) into four cohesive modules:

- :mod:`job_common`        — shared helpers, validation, ownership, visibility.
- :mod:`job_write_service` — create/duplicate/update + lifecycle + deadline sweep.
- :mod:`job_read_service`  — owner/public detail, preview, applyable lookups.
- :mod:`job_search_service`— industry scope, search filters, public/owner lists.

This facade re-exports every name that other modules and tests reference via
``from ...application import job_service`` / ``job_service.<name>`` /
``from ...application.job_service import <name>``, so the public import surface
is unchanged.

RBAC is enforced in the service layer (not routers) via ``PermissionChecker``
plus org-scoped tenant isolation: a partner only ever sees / mutates its own
org's jobs, and a cross-org access attempt returns ``404`` (never ``403``) so
the resource is not enumerable. Every write records an audit row.

Public discovery (:func:`list_public_jobs` / :func:`get_job` for non-owners)
returns **only** jobs that are published and visible to the principal's tier
(``docs/BUSINESS_LOGIC.md`` §5). Hidden/unpublished jobs return ``404`` to
non-owners to prevent enumeration; counts reflect visible records only.
"""

from __future__ import annotations

from app.modules.opportunities.application.job_common import (
    _RESOURCE,
    _audit_ctx,
    _can_moderate,
    _effective,
    _is_publicly_visible,
    _jsonable,
    _load_owned_job,
    _normalize_locations,
    _now,
    _public_filter,
    _unique_slug,
    _use_for_update,
    _validate_fields,
    _validate_salary_and_experience_modes,
)
from app.modules.opportunities.application.job_read_service import (
    _PREVIEW_PERSONAS,
    _record_detail_view_metric,
    get_applyable_job,
    get_applyable_job_ref,
    get_job,
    preview_job,
)
from app.modules.opportunities.application.job_search_service import (
    _apply_search_filters,
    _attach_student_fit,
    _empty_student_fit,
    _fit_tier,
    _job_fit_projection,
    _location_contains,
    _location_contains_any,
    _public_sort_order,
    _split_codes,
    list_my_jobs,
    list_public_jobs,
    resolve_industry_scope,
)
from app.modules.opportunities.application.job_write_service import (
    _DUPLICATE_COPY,
    _UPDATABLE,
    _notify_partner_auto_closed,
    _transition,
    check_jd_quality,
    close_job,
    create_job,
    delete_job,
    duplicate_job,
    reopen_job,
    submit_job,
    sweep_deadline_closures,
    update_job,
)

__all__ = [
    # write / lifecycle
    "create_job",
    "duplicate_job",
    "update_job",
    "check_jd_quality",
    "submit_job",
    "close_job",
    "reopen_job",
    "delete_job",
    "sweep_deadline_closures",
    # read / detail
    "get_job",
    "preview_job",
    "get_applyable_job",
    "get_applyable_job_ref",
    # search / discovery
    "list_public_jobs",
    "list_my_jobs",
    "resolve_industry_scope",
    # shared helpers (imported by jd_ai_service / referenced in docs & tests)
    "_load_owned_job",
    "_validate_fields",
    "_RESOURCE",
    "_now",
    "_audit_ctx",
    "_use_for_update",
    "_unique_slug",
    "_normalize_locations",
    "_effective",
    "_validate_salary_and_experience_modes",
    "_can_moderate",
    "_is_publicly_visible",
    "_jsonable",
    "_public_filter",
    # write-service internals
    "_transition",
    "_notify_partner_auto_closed",
    "_UPDATABLE",
    "_DUPLICATE_COPY",
    # read-service internals
    "_record_detail_view_metric",
    "_PREVIEW_PERSONAS",
    # search-service internals
    "_apply_search_filters",
    "_split_codes",
    "_location_contains",
    "_location_contains_any",
    "_public_sort_order",
    "_fit_tier",
    "_job_fit_projection",
    "_empty_student_fit",
    "_attach_student_fit",
]

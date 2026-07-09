"""Partner Dashboard V2 ``rbac_summary`` widget (spec §"Partner Dashboard V2
Contract" -> ``rbac_summary``): the acting principal's own capability grants,
plus which dashboard widgets are hidden/disabled because a grant is missing.

This is a READ-ONLY summary over the same ``permission_checker`` every service
already uses to gate writes — it never invents a parallel authorization path.
Partner Admin holds the org wildcard (``*:*``) and therefore always shows every
capability as granted; a non-admin member's grants come from
``organization.grant_resolver`` (already resolved onto ``principal.permissions``
by the auth dependency before this ever runs).
"""

from __future__ import annotations

import uuid

from app.shared.permissions import Principal, permission_checker

# (capability_key, resource, action, widget_key) — the capability rows surfaced
# on the Partner Dashboard V2. ``widget_key`` is the dashboard widget this grant
# unlocks, so the frontend can render an honest "locked: missing X" reason.
_CAPABILITY_ROWS: list[tuple[str, str, str, str]] = [
    ("analytics:view_job_metrics", "analytics", "view_job_metrics", "job_performance"),
    ("analytics:view_clicks", "analytics", "view_clicks", "job_performance_clicks"),
    ("analytics:export", "analytics", "export", "export_analytics"),
    ("candidate_identity:view_cv", "candidate_identity", "view_cv", "cv_preview"),
    ("candidate_identity:download_cv", "candidate_identity", "download_cv", "cv_download"),
    (
        "candidate_identity:request_reveal",
        "candidate_identity",
        "request_reveal",
        "identity_reveal",
    ),
    ("applications:read", "applications", "read", "pipeline_and_candidates"),
    ("pipeline:move_candidate", "pipeline", "move_candidate", "pipeline_actions"),
    ("members:read", "members", "read", "team_activity"),
    ("billing:view", "billing", "view", "billing"),
]


def capability_summary(principal: Principal, *, org_id: uuid.UUID | None) -> dict:
    grants: dict[str, bool] = {}
    hidden_widgets: list[str] = []
    for key, resource, action, widget in _CAPABILITY_ROWS:
        granted = permission_checker.can(principal, resource, action, resource_org_id=org_id)
        grants[key] = granted
        if not granted and widget not in hidden_widgets:
            hidden_widgets.append(widget)
    return {
        "is_org_admin": principal.is_superadmin or "*:*" in principal.permissions,
        "grants": grants,
        "hidden_widgets": hidden_widgets,
    }

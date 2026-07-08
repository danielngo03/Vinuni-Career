"""Permission catalog, system-admin wildcard, slugify, and friendly labels.

Permission strings are ``"{resource}:{action}"`` (matched by
``app.shared.permissions._matches`` with ``*`` wildcards). Resource nouns are
plural to stay consistent with the live matcher and ``auth/domain/personas.py``.
The DB ``permissions`` rows store ``resource_type`` + ``action``; the catalog
here is the *legal vocabulary* enforced when a role's grants are authored
(ADR-0002 §4).
"""

from __future__ import annotations

import re
import unicodedata

# resource -> allowed actions. ``partners`` is university-org only (review flow).
PERMISSION_CATALOG: dict[str, frozenset[str]] = {
    "organizations": frozenset({"read", "update"}),
    "roles": frozenset({"read", "create", "update", "delete"}),
    "departments": frozenset({"read", "create", "update", "delete"}),
    "members": frozenset({"read", "invite", "update", "remove"}),
    "jobs": frozenset(
        {
            "read",
            "create",
            "update",
            "delete",
            "submit",
            "publish",
            "moderate",
            # Owner reassignment (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md` jobs row) —
            # distinct from `update` so it can be granted narrowly (e.g. a team
            # lead role) without full job edit rights. Also the default capability
            # the visual workflow builder's ``assign_owner`` node requires.
            "assign_owner",
        }
    ),
    "events": frozenset(
        {"read", "create", "update", "submit", "moderate", "register", "manage"}
    ),
    # Application read/write surface (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`
    # `applications` row). `read` is the base partner-of-org gate reused by
    # every recruitment write (`decision_service`, `interview_service`,
    # `offer_service`, `scorecard_service`); `update` covers the applicant's own
    # withdraw/reveal-response actions (granted to the `student` persona
    # baseline, not partner roles); `review`/`reject`/`bulk_review`/`export` are
    # additive partner-grantable actions for a future finer-grained decision gate.
    "applications": frozenset(
        {"read", "update", "review", "reject", "bulk_review", "export"}
    ),
    # ``manage`` covers CRM oversight of an existing partner org: campus
    # relationship owner assignment, risk/trust flags, and university-only notes
    # (B-553). Distinct from ``approve``/``reject`` (registration review).
    "partners": frozenset({"read", "approve", "reject", "manage"}),
    # Advertising / sponsored placements (ADR-0009). Partner verbs:
    # view/create/edit/submit/manage; university oversight verb: moderate.
    "advertising": frozenset(
        {"view", "create", "edit", "submit", "manage", "moderate"}
    ),
    # Subscriptions / manual billing (ADR-0010). Self-service subscriber verbs:
    # view/subscribe; university oversight verb: moderate; plan admin: manage.
    "billing": frozenset({"view", "subscribe", "manage", "moderate"}),
    # Admin AI provider/model/budget governance (ADR-0011). University-org admins
    # (or superadmin) read effective settings (``read``) and edit aliases/flags/
    # budget/toggles + kill switch (``manage``). Invisible to students/partners.
    "ai_settings": frozenset({"read", "manage", "view_provider_identity"}),
    # University-managed CV template catalogue. Students only consume active
    # templates through /cv-templates; this admin surface is university-only.
    "cv_templates": frozenset({"read", "create", "update"}),
    # Company reviews (ADR-0013). University oversight verb: moderate. Slice-1
    # gates review moderation on the university-moderator proxy (`jobs:moderate`
    # + org_type=university); a dedicated `reviews:moderate` grant on university
    # roles is a later refinement. The system Admin wildcard already covers it.
    "reviews": frozenset({"moderate"}),
    # Visual workflow builder (account-approval automation engine, E23).
    "workflow": frozenset({"create", "read", "update", "activate"}),
    # Recruiting analytics (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`). Gates job
    # view/click metrics and export, independent of raw `applications:read`.
    "analytics": frozenset({"view_job_metrics", "view_clicks", "export"}),
    # Org audit-log read (B-518/523). Distinct from `members:*` so it can be
    # granted narrowly (e.g. a compliance-only role) without member management.
    "audit": frozenset({"read"}),
    # Shared industry/career-field taxonomy governance (P2/WS2.4). The taxonomy
    # is a GLOBAL (non-org-scoped) list; only the university control plane governs
    # it. Reads are public. Writes require this grant AND — like `support`/
    # `privacy`/`abuse` — an acting **university** org, so a partner Admin holding
    # `*:*` can never mutate it (`principal.is_superadmin` bypasses as usual).
    "taxonomy": frozenset({"manage"}),
    # AI-assisted recruiting actions (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`).
    # These are advisory/confirmation-required AI writes; the grant controls
    # who may even request them. No provider/model internals ever leave here.
    "ai_recruiting": frozenset(
        {
            "draft_jd",
            "screen_candidate",
            "suggest_scorecard",
            "move_candidate_with_confirmation",
        }
    ),
    # Sensitive candidate-identity access (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`
    # `candidate_identity` row). Gates the anonymous-apply reveal request and CV
    # preview/download independent of the broader `applications:read` surface —
    # every grant use is audited via `partner_candidate_access_events`.
    "candidate_identity": frozenset(
        {"request_reveal", "view_revealed_identity", "view_cv", "download_cv"}
    ),
    # Pipeline stage actions (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md` `pipeline`
    # row): advancing/rolling back a candidate's stage and configuring an org's
    # stage template. Distinct from `applications:*` so a narrow "pipeline
    # coordinator" role need not also hold application review/reject rights.
    "pipeline": frozenset(
        {"read", "move_candidate", "rollback", "configure_template"}
    ),
    # Scorecard evaluation actions (ADR-0005/ADR-0006; `docs/
    # PARTNER_RBAC_ANALYTICS_SPEC.md` `scorecards` row). `submit` covers both
    # submit and author-only withdraw; `read` covers the anchored partner list;
    # `read_aggregate`/`configure` are additive for a future dedicated
    # aggregate-only viewer / criteria-template editor role.
    "scorecards": frozenset({"read", "submit", "read_aggregate", "configure"}),
    # Interview scheduling actions (ADR-0006; `docs/
    # PARTNER_RBAC_ANALYTICS_SPEC.md` `interviews` row). `schedule` covers both
    # the initial schedule and in-place reschedule/edit; `read` covers the
    # partner-internal list.
    "interviews": frozenset({"schedule", "assign", "complete", "cancel", "read"}),
    # Offer lifecycle actions (ADR-0007; `docs/PARTNER_RBAC_ANALYTICS_SPEC.md`
    # `offers` row). `create` covers create/edit-draft/submit-for-approval and
    # the partner-internal list.
    "offers": frozenset({"create", "approve", "send", "rescind"}),
    # University career-services counselor workspace (B-554). Grantable per
    # counselor/role/department, mirroring the partner analytics/CV-access nouns
    # in ``docs/PARTNER_RBAC_ANALYTICS_SPEC.md`` — never hardcoded to a role name.
    "career_services_cohorts": frozenset({"read", "create", "update", "delete"}),
    "career_services_at_risk": frozenset({"read", "create", "update"}),
    "career_services_cv_review": frozenset({"read", "create", "update", "assign"}),
    "career_services_appointments": frozenset(
        {"read", "create", "update", "cancel"}
    ),
    "career_services_notes": frozenset({"read", "create", "update"}),
    "career_services_interventions": frozenset({"read", "create", "update"}),
    "career_services_reporting": frozenset({"read"}),
    # Notification/email template governance
    # (`docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` §4). University Admin
    # manages default/global templates; a Partner Admin (or a delegated
    # recruiter with a granted permission) may manage templates scoped to
    # their own org only — never another org's templates.
    "notification_templates": frozenset(
        {"read", "create", "update", "activate", "archive"}
    ),
    # Platform trust — support console, privacy/compliance, abuse/fraud
    # (ADR-0014, E36). No new hardcoded role: grantable on any university-org
    # role like `jobs:moderate`; every service gate additionally requires
    # `org_reporting_facade.is_university_org` so a misconfigured partner role
    # can never hold these even if granted by mistake (`principal.is_superadmin`
    # bypasses as usual). `platform_support` module: `support:*`. `compliance`
    # module: `privacy:*`. `moderation` module extension: `abuse:*`.
    "support": frozenset({"read", "act", "escalate"}),
    "privacy": frozenset({"read", "process"}),
    "abuse": frozenset({"read", "triage", "escalate", "override"}),
}

# The single all-access grant tuple stored on a system Admin role.
ADMIN_WILDCARD_RESOURCE = "*"
ADMIN_WILDCARD_ACTION = "*"
ADMIN_WILDCARD = "*:*"

# System role names (immutable: cannot be renamed/deleted, *:* cannot be removed).
SYSTEM_ADMIN_ROLE_NAME = "Admin"

TRUST_LEVELS = frozenset({"standard", "verified", "strategic"})
RISK_FLAG_SEVERITIES = frozenset({"low", "medium", "high"})
SUBSCRIPTION_TIERS = frozenset({"free", "basic", "premium", "enterprise"})
ORG_TYPES = frozenset({"partner", "university"})


def is_catalog_permission(resource: str, action: str) -> bool:
    """True if ``(resource, action)`` is the admin wildcard or in the catalog."""

    if resource == ADMIN_WILDCARD_RESOURCE and action == ADMIN_WILDCARD_ACTION:
        return True
    allowed = PERMISSION_CATALOG.get(resource)
    return allowed is not None and action in allowed


def slugify(value: str) -> str:
    """ASCII-fold + lowercase a display name into a URL-safe slug fragment."""

    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    return slug or "org"


# Friendly status labels (never expose raw enum codes to end users).
_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "pending": "Đang chờ",
        "active": "Đang hoạt động",
        "suspended": "Tạm ngưng",
        "pending_review": "Đang chờ duyệt",
        "approved": "Đã duyệt",
        "rejected": "Đã từ chối",
    },
    "en": {
        "pending": "Pending",
        "active": "Active",
        "suspended": "Suspended",
        "pending_review": "Pending review",
        "approved": "Approved",
        "rejected": "Rejected",
    },
}

_MEMBER_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {"active": "Đang hoạt động", "suspended": "Tạm ngưng", "left": "Đã rời"},
    "en": {"active": "Active", "suspended": "Suspended", "left": "Left"},
}

_INVITE_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "pending": "Đang chờ",
        "accepted": "Đã chấp nhận",
        "revoked": "Đã thu hồi",
        "expired": "Đã hết hạn",
    },
    "en": {
        "pending": "Pending",
        "accepted": "Accepted",
        "revoked": "Revoked",
        "expired": "Expired",
    },
}


def status_label(status: str, *, locale: str = "vi") -> str:
    return _STATUS_LABELS.get(locale, _STATUS_LABELS["vi"]).get(status, status)


def member_status_label(status: str, *, locale: str = "vi") -> str:
    return _MEMBER_STATUS_LABELS.get(locale, _MEMBER_STATUS_LABELS["vi"]).get(
        status, status
    )


def invite_status_label(status: str, *, locale: str = "vi") -> str:
    return _INVITE_STATUS_LABELS.get(locale, _INVITE_STATUS_LABELS["vi"]).get(
        status, status
    )

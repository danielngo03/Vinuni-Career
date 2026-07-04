# Partner RBAC & Recruiting Intelligence Spec

> Last updated: 2026-07-02
> Purpose: define partner-admin ownership, grantable recruiter capabilities, and the analytics/read models needed for a serious partner recruiting command center.

## Product Principle

Partner Admin has all partner-organization capabilities by default. Other partner members do not get features because of hardcoded role names; they receive capabilities through configurable RBAC assignments by user, role, and department.

This means features such as job analytics, CV access, click metrics, billing, pipeline actions, AI screening, exports, and team management must be permission-gated and auditable. The UI may surface entry points, but the backend service layer owns final authorization.

## Current Backend Inventory

Already present:

- `organization`: organizations, members, roles, permissions, departments, invitations, membership role/department assignment.
- `billing`: partner/org subscriptions, plans, manual billing, limit facade.
- `opportunities`: job lifecycle, moderation, public/ranking reads, `view_count` on job ranking data.
- `recruitment`: applications, anonymous reveal flow, pipeline stages, scorecards, interviews, offers, job invitations.
- `dashboards`: partner dashboard read model with active/draft/pending jobs, total applications, pending reveals, jobs needing attention, recent applications.
- `audit_logs`: shared audit writer used by many write paths.
- `ai_assistant`: partner tools for jobs, pipeline summary, candidate search/detail, JD drafting/rewrite/bias check, scorecard suggestion, screening brief.

Known gap: the partner dashboard endpoint does not yet expose per-job impression/view/click/apply conversion, owner activity, CV access events, or department-scoped analytics.

## Required Capability Model

Add or confirm these permission nouns/actions in the organization permission catalog and service checks:

| Capability | Example Actions | Scope |
|---|---|---|
| `analytics` | `view_job_metrics`, `view_clicks`, `export` | org, department, job |
| `applications` | `read`, `review`, `reject`, `bulk_review`, `export` | org, department, job |
| `candidate_identity` | `request_reveal`, `view_revealed_identity`, `view_cv`, `download_cv` | org, job, application |
| `jobs` | `create`, `update`, `submit`, `close`, `duplicate`, `assign_owner` | org, department, job |
| `pipeline` | `read`, `move_candidate`, `rollback`, `configure_template` | org, department, job |
| `scorecards` | `read`, `submit`, `read_aggregate`, `configure` | org, job, stage |
| `interviews` | `schedule`, `assign`, `complete`, `cancel` | org, job, application |
| `offers` | `create`, `approve`, `send`, `rescind` | org, job, application |
| `members` | `read`, `invite`, `update`, `remove` | org |
| `roles` / `departments` | `read`, `create`, `update`, `delete` | org |
| `billing` | `view`, `subscribe`, `manage` | org |
| `ai_recruiting` | `draft_jd`, `screen_candidate`, `suggest_scorecard`, `move_candidate_with_confirmation` | org, job, application |

Partner Admin should carry a wildcard grant for the org. Non-admin members should be assigned only the grants their role/department needs.

## Recruiting Intelligence Read Models

Build read models instead of heavy dashboard joins.

### `partner_job_metrics_daily`

Per org/job/date counters:

- `impressions`
- `detail_views`
- `cta_clicks`
- `apply_starts`
- `applications_submitted`
- `save_clicks`
- `share_clicks`
- `source` breakdown: organic, search, recommendation, sponsored, invitation, direct/referral
- coarse dimensions only: device class, student tier, major group, year group. No PII, raw IP, raw user-agent, or exact location.

### `partner_candidate_access_events`

Append-only audit/read model for sensitive candidate access:

- actor user/org/department
- application/job/candidate identifiers
- event type: application_opened, cv_previewed, cv_downloaded, identity_reveal_requested, identity_revealed_viewed
- reason/context where required
- timestamp

This powers "who viewed which CV" and supports export/security review.

### `partner_activity_feed`

Admin-facing org activity:

- job created/submitted/updated/closed
- candidate reviewed/rejected/moved
- scorecard submitted/withdrawn
- interview scheduled/completed/cancelled
- offer created/sent/rescinded
- role/member/department/billing changes

The feed must be filtered by the viewer's grants and department scope.

## Partner Dashboard V2 Contract

Extend `GET /dashboards/partner` or add `GET /dashboards/partner/ops` with:

- `todos`: prioritized tasks from jobs, reveals, pipeline SLA, interviews, offers, billing/package limits, and team setup.
- `metrics`: current metrics plus conversion metrics when the analytics projection exists.
- `job_performance`: top/at-risk jobs with applications, views, clicks, conversion rate, source mix, and owner.
- `team_activity`: recent org activity filtered by permission.
- `access_alerts`: unusual CV downloads, reveal spikes, or permission-sensitive events.
- `rbac_summary`: current actor permissions and which widgets are hidden/disabled because grants are missing.
- `ai_recommendations`: advisory only; any write action remains confirmation-required and audited.

All widgets must degrade independently and never fabricate data. If click/view projections are absent, the UI must say it is using application counts only.

## Frontend Rules

- Do not label a surface "admin-only" unless the backend truly hard gates it to admin. Prefer "Permissions & operations" or "Team access".
- Show capability entry points only when useful, but rely on backend 403 for final enforcement.
- When a widget requires a grant the actor lacks, prefer a quiet locked/disabled state with a short reason, not fake zeros.
- Dashboard cards must link into real workflows: jobs, candidates, pipeline, analytics, team, billing, company profile, settings.
- AI widgets must be advisory unless paired with a confirmation card.

## Visual Recruiting Workflow Builder Contract

Partner and university workflow configuration must be a real visual builder, not
only a list of static settings or hardcoded pipeline templates.

Allowed flow owners:

- Partner org: recruiting workflows for jobs, applications, pipeline stages,
  interviews, offers, team approvals, candidate notifications, and AI-assisted
  screening actions.
- University org: moderation, partner approval, event approval, ad approval,
  notification broadcasts, template governance, and operational escalations.

Required behavior:

- Canvas with nodes/edges, stage groups, validation, minimap/outline, and
  readable execution history.
- Draft, dry-run/test, activate, pause, archive, and clone flows.
- Active versions are immutable. Editing an active flow creates a new draft
  version.
- Node types include trigger, condition, wait/SLA, assign owner, send
  notification, create task, move candidate, request approval, AI suggestion,
  and webhook/integration where allowed.
- Consequential AI/write nodes are confirmation-required unless an org admin
  has explicitly enabled an audited automation policy for that exact node type.
- Activation requires RBAC grants for every action the flow can execute; users
  cannot activate flows that perform actions outside their scope.
- Every execution stores node logs with status, actor/system identity, reason,
  input summary, output summary, and user-safe error.
- Failed nodes create recoverable tasks instead of silently dropping candidates,
  applications, or notifications.
- Sensitive actions such as CV access, identity reveal, rejection, offer send,
  and billing/package changes require explicit permissions and audit rows.

Frontend requirements:

- The builder should feel like an operations tool: compact, inspectable, and
  predictable. Avoid oversized decorative cards.
- Show permission blockers before activation, not after a flow fails in
  production.
- Show dry-run output using sample events with PII redacted.
- Keep AI nodes visually distinct as advisory/confirmation-required, without
  exposing provider/model internals.

## Acceptance Criteria

- Partner Admin can grant/revoke feature access by role, user, and department.
- A member with analytics permission can see job views/clicks for their allowed scope; a member without it cannot.
- A member with CV permission can preview/download allowed CVs; every access is logged.
- Job performance metrics distinguish impressions, views, clicks, apply starts, applications, and conversion.
- Partner dashboard V2 uses only real read models and shows honest fallback copy while projections are missing.
- Integration tests cover tenant isolation, permission denial, department scope, audit rows, and PII-safe metric dimensions.

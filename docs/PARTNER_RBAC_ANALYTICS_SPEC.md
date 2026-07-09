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
- `recruitment`: applications (always identified — no anonymous/reveal flow, owner decision 2026-07-10), pipeline stages, scorecards, interviews, offers, job invitations.
- `dashboards`: partner dashboard read model with active/draft/pending jobs, total applications, new/unreviewed applications, jobs needing attention, recent applications.
- `audit_logs`: shared audit writer used by many write paths.
- `ai_assistant`: partner tools for jobs, pipeline summary, candidate search/detail, JD drafting/rewrite/bias check, scorecard suggestion, screening brief.

Known gap: the partner dashboard endpoint does not yet expose per-job impression/view/click/apply conversion, owner activity, CV access events, or department-scoped analytics.

## Required Capability Model

Add or confirm these permission nouns/actions in the organization permission catalog and service checks:

| Capability | Example Actions | Scope |
|---|---|---|
| `analytics` | `view_job_metrics`, `view_clicks`, `export` | org, department, job |
| `applications` | `read`, `review`, `reject`, `bulk_review`, `export` | org, department, job |
| `candidate_access` | `open_application`, `view_contact`, `view_cv`, `download_cv` | org, job, application |
| `jobs` | `create`, `update`, `submit`, `close`, `duplicate`, `assign_owner` | org, department, job |
| `pipeline` | `read`, `move_candidate`, `rollback`, `configure_template` | org, department, job |
| `scorecards` | `read`, `submit`, `read_aggregate`, `configure` | org, job, stage |
| `interviews` | `schedule`, `assign`, `complete`, `cancel` | org, job, application |
| `offers` | `create`, `approve`, `send`, `rescind` | org, job, application |
| `members` | `read`, `invite`, `update`, `remove` | org |
| `roles` / `departments` | `read`, `create`, `update`, `delete` | org |
| `billing` | `view`, `subscribe`, `manage` | org |
| `ai_recruiting` | `draft_jd`, `screen_candidate`, `suggest_scorecard`, `move_candidate_with_confirmation` | org, job, application |
| `talent_pool` | `search`, `search_external_jd`, `save_candidate`, `add_to_pipeline`, `export` | org, department |

Partner Admin should carry a wildcard grant for the org. Non-admin members should be assigned only the grants their role/department needs.

## Talent Pool — AI Semantic Candidate Search Contract

(Owner decision 2026-07-10.) Talent Pool is an AI semantic candidate-search
surface, not a masked "blind-search" card wall. There is no anonymity/reveal
gate; authorized recruiters search and see identified candidates, and every
sensitive access is RBAC-gated and audited exactly like application CV access.

Retrieval pipeline:

1. Candidate CVs (owned/consented, indexable talent) are embedded into a
   pgvector store. Embeddings are refreshed when a candidate's active CV changes.
2. A query — a recruiter's typed brief, an existing posted job, OR a pasted /
   uploaded **external JD that is not yet a posted job** — is embedded and run as
   dense semantic search over the candidate index.
3. Structured filters narrow the candidate set: skills, experience level/years,
   major/faculty, graduation cohort, location/work-mode, availability, and tier.
   Filters are deterministic and apply before and after semantic ranking.
4. An LLM rerank pass orders the top candidates and returns **human-readable
   match reasons** (why each candidate fits the JD/brief) plus evidence gaps —
   never a raw similarity number.

External-JD search:

- A recruiter may paste or upload a JD (PDF/text) that has no corresponding
  posted job. The JD runs through the same extraction/embedding path used for
  posted jobs and returns ranked candidates with match reasons.
- External-JD searches are quota-metered like other AI recruiting actions and
  are audited (actor, org/department, JD hash/reference, result count).

Privacy and safety:

- Never expose provider/model names, embedding vectors, similarity scores,
  token counts, prompts, or any AI internals to partners. Match output is a
  product-facing reason string plus deterministic filter/skill evidence only.
- Candidate visibility respects the student's passive-search/discoverability
  consent setting where the product requires opt-in; opting out removes the
  candidate from the index, it does not mask them into an anonymous card.
- CV preview/download from a talent-pool result uses the same `candidate_access`
  RBAC, watermark, and audit rules as application CV access.
- Fallback when the AI gateway/embeddings are unavailable: deterministic
  keyword + structured-filter search with an honest "AI ranking unavailable"
  state, never fabricated matches or reasons.

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
- event type: application_opened, contact_viewed, cv_previewed, cv_downloaded
- reason/context where required
- timestamp

This powers "who viewed which CV" and supports export/security review. Candidate
access is always to an identified candidate; there is no reveal-request event
because there is no anonymity gate to unlock (owner decision 2026-07-10).

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

- `todos`: prioritized tasks from jobs, new applications, pipeline SLA, interviews, offers, billing/package limits, and team setup.
- `metrics`: current metrics plus conversion metrics when the analytics projection exists.
- `job_performance`: top/at-risk jobs with applications, views, clicks, conversion rate, source mix, and owner.
- `team_activity`: recent org activity filtered by permission.
- `access_alerts`: unusual CV downloads, CV-view spikes, or permission-sensitive events.
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
- Sensitive actions such as CV access/download, rejection, offer send,
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

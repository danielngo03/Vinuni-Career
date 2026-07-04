# Product Reality Rebuild Spec — VinUni Career Platform

> Last updated: 2026-07-04
> Purpose: prevent agents from building demo-like screens, generic CRUD, fake
> metrics, or form-heavy workflows that do not match how a real recruiting
> ecosystem works.

This spec is a cross-product reality gate. Use it before broad implementation,
before marking a slice complete, and whenever a screen or backend flow feels
technically present but not useful enough for real students, partners, or
university operators.

## 1. Product Principle

VinUni Career is not a job board with dashboards. It is the operating system for
career discovery, CV creation, applications, recruiting operations, events,
partner monetization, university governance, and AI-assisted decision support.

Every major feature must answer:

- Who is doing real work here?
- What decision or task becomes easier?
- What data is required to make it truthful?
- What happens when data is missing, stale, denied, pending, duplicated, or
  low-confidence?
- What is automated, what requires human confirmation, and what requires
  university/partner approval?
- How does the system preserve privacy, auditability, and rollback?

If those answers are unclear, do not code the feature as a placeholder. Route it
through product + architecture and document the contract first.

## 2. Cross-System Reality Checklist

### Account, Auth, Onboarding

- A registered email must have one canonical account identity. Duplicate
  registration must be blocked or safely resumed if verification is pending.
- OAuth accounts must link to existing email accounts with explicit conflict and
  account-linking states.
- Email verification and password reset must support configured OTP and link
  flows, expiry, resend cooldown, rate limiting, too-many-attempt handling, and
  non-enumerating copy.
- Verification and recovery UI must be concise and operational: a top-left
  back action returns to the previous form, preserves safe fields such as email,
  never shows decorative-only icons, and never displays attempt-count claims
  unless backed by backend policy.
- Email templates must not assume `name` exists before onboarding is complete.
- Onboarding is a state machine. It should preserve draft progress, support
  resume, and mark completion without deleting audit/support history.
- Profile data is not a prerequisite for CV creation. Ask for profile fields
  only when they are necessary for a workflow or can be inferred/reviewed from
  an uploaded CV.

### Student CV And Career Workspace

- CV Studio is a visual document editor first. Long forms are secondary
  metadata/fallback tools, not the primary authoring experience.
- Students must be able to upload an existing CV, choose a visual template,
  duplicate a CV, import reviewed extraction, or use AI/raw notes to populate a
  template.
- University can publish official templates by discipline/career track, with
  versioning, preview, ownership, and archive/publish workflow.
- The editor must support inline text editing, selectable blocks, drag/drop
  reorder, photo replace/crop, page-break warnings, undo/redo, autosave, version
  restore, export preview, and PDF export consistency.
- AI CV edits are command-to-patch actions. They return structured diffs and are
  applied only after student confirmation.
- CV library limits, archived CVs, duplicate uploads, stale CV warnings, and
  application snapshots must be enforced by backend services.

### Jobs, JD Data, And Eligibility

- Job posting data must support realistic requirements: level, experience,
  education, major/industry taxonomy, skills, languages, work authorization,
  nationality, gender, age range/min/max/no requirement, marital status/no
  requirement, location mode, multiple locations, deadline, hiring seats, and
  partner-specific screening questions.
- Salary must be structured, not display-string-only: negotiable, hidden,
  fixed, range, from, to, currency, period, gross/net if available, and display
  formatting such as `30 - 60 triệu`, `Tới 50 triệu`, or `Thỏa thuận`.
- Experience must be structured: no requirement, student/fresher, exact range,
  minimum, maximum, and display formatting such as `Không yêu cầu`, `1 - 3 năm`,
  or `Từ 2 năm trở lên`.
- Locations must link to canonical province/district/ward data and support
  post-2025 Vietnam administrative changes. UI can show compact labels, but
  filters need real IDs and multi-select behavior.
- Public job detail must be truthful for guests. Logged-in student detail adds
  personalized CV fit, competition guidance, saved/apply state, and recommended
  next action.

### Matching, Competition, And Learning Guidance

- CV-JD matching is a product score, not raw model confidence. It should combine
  extracted CV facts, job requirements, skills, experience/education/location
  alignment, freshness, and evidence quality.
- The system should recommend the best eligible CV for a job and explain the
  gaps without encouraging fabricated claims.
- Competition intelligence is shown only to logged-in users and only when enough
  privacy-safe data exists. It must use aggregate/bucketed signals: seats,
  application volume, applicant quality distribution, student fit bucket,
  deadline, source mix, and recent activity.
- Never show exact rank, other candidates' PII, raw scores, prompt/model
  internals, or deterministic claims such as "you will be hired".
- Learning guidance should map gaps to realistic skills/courses/resources,
  preferably university-approved or partner-relevant content, with fallback to
  generic suggestions when no curated resource exists.

### Applications And Candidate Journey

- Applications must snapshot the submitted CV, answers, job requirements,
  student consent, and visible job/company fields at submission time so later JD
  edits do not rewrite history.
- Students need a real application workspace: draft apply, submitted, viewed,
  in review, interview, offer, rejected, withdrawn, hired, and archived states
  with timestamps, next action, messages, interviews, documents, and withdrawal
  policy.
- Duplicate applications must be blocked or explicitly resumed. A student should
  never accidentally submit the same CV to the same job twice.
- Screening questions need typed answers, required/optional flags, validation,
  partner visibility rules, and application snapshot storage.
- Interview and offer milestones must be visible to both student and partner
  with permission-safe details, calendar/reminder hooks, reschedule/cancel
  states, and audit.
- Student-facing status copy must be honest. Do not imply the partner has read a
  CV unless backed by an event such as view/reveal/status transition.

### Partner Recruiting Operations

- Partner Admin has full organization control by default, but all capabilities
  must be grantable through RBAC by user, role, department, and scope.
- Partner team management must cover invite, role assignment, department
  assignment, permission preview, revoke, inactive users, audit, and ownership
  transfer.
- Recruiting workflows should be visual and versioned: node palette, canvas,
  inspector, validation, dry run, immutable active versions, execution logs,
  failed-node recovery tasks, and permission blockers.
- Candidate pipeline must support real ATS behavior: optimistic concurrency,
  scorecards, interviews, notes, offers, rejections, withdrawals, bulk actions,
  SLA reminders, and audit logs.
- CV access, contact reveal, exports, analytics, billing, AI actions, and
  candidate movement must be RBAC-gated and audited.
- Job analytics should include impressions, detail views, save clicks,
  apply-starts, applications, source mix, conversion funnel, channel/sponsored
  attribution, and candidate quality buckets when privacy-safe.
- Partner job creation must behave like a recruiting workflow: draft, JD
  quality checks, structured requirement capture, preview as guest/student,
  quota/plan validation, moderation submit, approval/rejection handling,
  clone-from-performing-job, and amendment policy after publication.
- Employer CRM should cover company profile quality, verified identity,
  recruiter seats, campus relationship owner, event history, campaign history,
  hiring outcomes, and risk/trust signals.

### University Operations

- University is the trust/governance layer, not a passive admin panel.
- Required operations include partner approval/trust level, job/event/ad
  moderation, template governance, notification template governance, student
  tier/eligibility policy, AI provider policy, reporting exports, audit review,
  incident/support view, and career outcomes tracking.
- University staff roles must be configurable and service-layer enforced. Do
  not hardcode staff role names.
- Moderation and approval queues need status, SLA, assignee, reason codes,
  escalation, bulk action, and audit trail.
- Official CV templates, career resources, learning paths, and events should be
  managed as publishable content with versioning and review.
- Career services need counselor workflows: student cohorts, at-risk students,
  CV review queues, appointment scheduling, employer relationship notes,
  outcome tracking, and intervention history.
- University analytics should separate platform adoption, student outcomes,
  employer engagement, event performance, moderation health, and AI usage/cost.
  Any sensitive student slice must be aggregated or permission-gated.

### Discovery, Search, Recommendations, Ads

- Public and student discovery must separate organic, recommended, sponsored,
  and university-curated inventory. Sponsored placement labels are mandatory.
- Recommendation rails must be backed by real contracts: reason codes,
  source type, score bucket, fallback source, and session/user signal boundary.
- Guest personalization can use privacy-safe session behavior; logged-in
  personalization can use saved jobs, CV/job fit, searches, applications, and
  preferences.
- Search and filters must support category taxonomy, keyword, company, skills,
  location, job type, work mode, salary, experience, education, level,
  publication date, sponsor/featured facets where appropriate, sort, and
  pagination.
- Hierarchical filters need precise semantics. Selecting a parent means all
  descendants; selecting a child or specialty narrows to that child and must not
  also OR-match the parent as a separate broad filter. Hover/focus may reveal
  child columns, but the applied query should be the deepest selected scope.
- Location and taxonomy pickers should stay anchored to the triggering filter,
  fit within the viewport, allow search and multi-select, and use canonical IDs
  rather than display text.
- Advanced filters should be a compact menu/popover near the filter toolbar when
  the task is quick refinement; use a full screen or side panel only for deep
  configuration flows.
- Ads and banners need placement, creative approval, targeting scope,
  impression/click/apply-start tracking, frequency caps, and disclosure.

### Events, Messaging, Notifications

- Events must handle public/invite-only visibility, seat capacity, waitlist,
  ticket type, sponsor placement, registration, check-in, QR, cancellation,
  reminders, and post-event follow-up.
- Messaging is institutional: student-partner/university communication around
  applications, events, and support. Avoid generic social chat.
- Notifications need category, priority, in-app/email/push channel, preferences,
  mandatory vs optional policy, outbox retry/backoff/dead-letter, template
  variable validation, and localized copy.
- Notification and message screens should be full product surfaces when the task
  requires workflow context, not modal-only side panels.

### Billing, Packages, Quotas

- Partner packages, student tiers, AI quota, job posting quota, spotlight slots,
  passive search, email blasts, team member caps, and template/pipeline limits
  must be configurable and enforced by backend services.
- Billing UI must show current plan, usage, overage/upgrade path, manual payment
  status, invoices/receipts, pending downgrade/cancel state, and proration.
- Quota warnings and failures must be visible before users lose work.

### Platform Admin, Support, And Compliance

- Superadmin/platform support tools must exist for tenant lookup, account state,
  verification state, outbox health, failed async jobs, moderation escalations,
  abuse reports, package overrides, and safe impersonation/support views.
- Support actions must be audited and scoped. Never expose raw secrets,
  refresh tokens, raw provider payloads, or hidden CV contents unless the role
  and consent path explicitly allow it.
- Privacy controls need consent capture, data export, retention/deletion
  policy, CV/application snapshot retention, notification preferences, and
  student-visible security history.
- Abuse/fraud controls should cover suspicious company profiles, misleading
  jobs, duplicate/spam applications, abusive messages, suspicious ad creatives,
  and manual escalation.

### AI Platform

- AI features must save real work: CV extraction, CV editing, job fit, learning
  gaps, interview preparation, JD quality check, workflow suggestions,
  notification drafting, moderation assistance, and support triage.
- Each AI task needs a permission class, prompt version, tool contract, eval
  dataset, deterministic fallback, cost/quota policy, provider secrecy, and
  rollback/confirmation rules.
- AI must never invent student facts, silently mutate CVs, finalize moderation,
  make hiring decisions, expose internals, or bypass RBAC.

### Data, Analytics, Observability

- Use canonical entities plus read models/projections for high-volume screens.
- Track product events with metadata-only payloads: impressions, clicks,
  saves, apply starts, application submits, CV exports, AI suggestions,
  workflow executions, notifications, and moderation decisions.
- No raw CV text, prompts, secrets, provider data, or PII in logs/analytics.
- Every async process needs retry/backoff/dead-letter or explicit manual
  recovery.
- Seed/crawled demo data must be clean, linked to taxonomy/location/company
  entities, use accurate logos/media, and represent varied salary/experience/
  location/eligibility cases.
- Data migration and seed scripts must be repeatable, idempotent where
  possible, environment-aware, and able to reset local demo data without
  corrupting migration history.
- Read models must define source events, refresh strategy, stale-data behavior,
  and fallback UI before they power dashboards, recommendations, or analytics.

### Frontend Product Quality

- Every first screen must show a real workflow: search, queue, editor, pipeline,
  review task, analytics insight, or next action.
- Avoid generic cards, fake dashboards, decorative charts, large empty heroes,
  and form-heavy flows where a visual/editor/workflow UI is expected.
- Use v9 Monochrome: black/white/gray hierarchy, restrained semantic color,
  Plus Jakarta Sans, consistent icons, no emoji UI icons, no decorative
  gradients/orbs.
- Inputs need one clean boundary, polished focus state, no harsh double border,
  clear label/error placement, and stable layout.
- Mobile, keyboard, screen-reader, loading, empty, error, permission, offline,
  and conflict states are part of completion.
- Shared shells must respect persona context: public/student headers optimize
  discovery, auth/onboarding stays calm and centered, partner/university/admin
  surfaces prioritize operational density, queues, permissions, and audit.
- Do not use the same generic table/card composition for list, detail, editor,
  workflow, analytics, and support screens. Pick the interaction model that
  matches the task: canvas, split pane, queue, kanban, timeline, inspector,
  command bar, or compact form.

## 3. Red Flags That Must Trigger Rework

- A student must fill many forms before creating or improving a CV.
- A dashboard has numbers that are not backed by read models or honest empty
  states.
- An AI feature produces prose but does not change or accelerate a real task.
- A recommendation is actually "recent" or "popular" but labeled as
  personalized.
- A partner admin capability is hardcoded to a role instead of grantable RBAC.
- A workflow builder is replaced by static settings forms.
- A public/student surface hides sponsored disclosure or mixes ads into organic
  results without labeling.
- A feature has no duplicate, permission, expiry, rate-limit, concurrency,
  async failure, or low-confidence path.
- A seed/crawl script creates disconnected, dirty, logo-less, or unrealistic
  data that makes UI review meaningless.

## 4. Required Output For Broad Agents

Before implementation, broad agents must produce:

- Current code reality by module/screen/API.
- Missing product logic and why it matters.
- Backend/data/API changes required before UI polish.
- Frontend IA and interaction changes required before visual polish.
- AI tasks that are useful, safe, and measurable.
- Tests/evals/browser checks required.
- What is in-scope now, backlog later, or explicitly not planned.

After implementation, agents must report:

- Source docs read.
- Contracts changed.
- Files changed.
- Tests/checks run.
- Remaining product risk.
- Verification tier: `implemented`, `API wired`, `browser verified`,
  `visual-design verified`, and/or `E2E verified`.

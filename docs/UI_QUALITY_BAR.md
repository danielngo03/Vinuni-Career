# UI Quality Bar — VinUni Career Platform

> Source of truth for visual polish, interaction quality, and release readiness of frontend surfaces.

## 1. Product UI Direction

- This is an operational education/career SaaS, not a marketing-only website.
- App screens prioritize fast scanning, dense but calm information, clear hierarchy, and repeat workflows.
- Use real product surfaces: tables, filters, forms, split panes, kanban boards, timelines, editors, previews, and actionable empty states.
- Decorative gradients, oversized hero composition, and soft card-heavy layouts are allowed only where `docs/DESIGN.md` explicitly calls for a public/brand surface.
- Every persona surface must be designed for its real job-to-be-done, not from
  one generic dashboard template.
- Public pages are marketplace/discovery surfaces, not brochure pages: jobs,
  events, companies, search, and sponsored placements must be visible as real
  product content.
- Discovery surfaces must feel intelligent: show organic, recommended,
  sponsored, and university-curated inventory with clear source labels, not one
  undifferentiated grid.
- For the public marketplace composition, `docs/DESIGN_EXAMPLE.png` is the
  required structural reference: enterprise recruiting nav, companies mega menu
  affordance, split hero with real media, overlay search, metric strip, job list,
  right rail, sponsored/event surfaces, and trust rail. Match the structure and
  density; keep VinUni colors and content.

## 2. Non-Negotiables

- No feature screen is complete with placeholder copy such as "will be implemented later".
- No fake dashboard numbers. Use real APIs, skeletons, empty states, permission states, or disabled TODO panels.
- No `alert()` / `confirm()` for product workflows. Use modal, toast, inline error, or confirmation drawer.
- No unaudited AI write action. Show pending diff and require explicit user confirmation.
- No sponsored/ad content without visible `Được tài trợ` or `Quảng cáo` disclosure.
- No "recommended" section is valid if it is actually a recent/new list without
  reason codes, fit score, session signal, or documented fallback label.
- No provider/model/token/prompt/internal AI details in user-facing UI.
- No public homepage is complete if it only contains hero copy, generic feature
  cards, or fake stats. It must show real public discovery surfaces or honest
  loading/empty/error states.
- No public marketplace is visually acceptable if the first two screens lack
  banner/carousel/spotlight merchandising, saved/invitation/feedback/AI quick
  actions, and dense scan-friendly job inventory. Passing build is not enough.
- No major UI redesign is complete without a `frontend-design` plan first:
  subject/audience/job, compact color/type/layout system, signature element,
  motion plan, self-critique, and `globals.css` light/dark/system theme audit.
- No persona dashboard is complete if it only shows welcome copy, generic KPI
  cards, or static navigation. It must include the persona's real queue, next
  action, critical alerts, and deep links to work.
- No student CV surface is complete if it forces profile-form completion before
  upload/template/AI/raw-notes flows, hides active CV quota, or lacks a path to
  choose/improve the best CV for a target job.
- No "browser verified" claim is valid for visual work unless screenshots or
  browser inspection were taken after a fresh app restart/build at 375px, 768px,
  1024px, and 1440px and compared against the relevant screen spec.

## 3. Layout Patterns

- CV Studio: CV library/template marketplace first; then builder with left
  template/section/elements navigator, center document-like editor, right A4
  preview / AI suggestion / job-fit panel; mobile uses tabs.
- Job apply: login intent preservation, CV selection modal, anonymous apply consent, screening question review, submit confirmation.
- Partner pipeline: board or dense table with filters, bulk actions, stage transition confirmation, audit trail access.
- University admin: moderation queues, policy controls, KPI dashboards, export/report flows, clear approval/rejection reasons.
- AI assistant: streaming message list, tool cards, source citations where applicable, confirmation cards for writes.
- Public career gateway: search-first hero, live public job list, event/company
  discovery, login-gated apply/save/register actions, and sponsored slots with
  non-removable labels.
- Student signed-in marketplace / command center: public marketplace top-nav
  inherited and personalized for student, CV readiness/quota, preferences
  readiness, next action, recommended jobs with recommended CV, saved jobs,
  applications/interviews, events, AI suggestions, notifications, and settings
  nudges.
- Partner recruiting ops: job health, candidate pipeline, interview schedule,
  team activity, quotas/packages, ads/events, and recent applications.
- University operations center: moderation queues, SLA risk, partner health,
  outcomes, AI/cost health, notification/template health, audit/security alerts.

## 4. Visual Quality

- Use VinUni tokens and Plus Jakarta Sans from `docs/DESIGN.md`.
- VinUni brand colors are anchors, not a requirement to saturate the product
  with every brand color. Use clean neutrals, action blues, teal/cyan AI/success
  accents, restrained red, and amber disclosure/status where they improve
  hierarchy and trust.
- Prefer flat, precise, readable SaaS UI over glassmorphism-heavy surfaces inside the app.
- Public/brand surfaces may use restrained enterprise gateway patterns: trust signals, clear persona paths, and conservative accent CTAs.
- Do not let dashboard screens become one-note blue/grey blocks; use status colors, neutral density, and clear hierarchy.
- "Beautiful" means usable under real data density: aligned columns, readable
  lists, stable toolbars, meaningful charts, and clear action hierarchy.
- Stable dimensions for cards, tables, toolbar buttons, counters, board columns, preview panes, and modals.
- Hover/focus states must not shift layout.
- Text must fit at 375px, 768px, 1024px, and 1440px.
- Icons must come from the project icon system and remain consistently sized.
- Overuse of `rounded-2xl`/large soft cards is a visual debt signal, especially
  on marketplace, dashboard, pipeline, and editor surfaces. Prefer 8-12px radii,
  table/list density, stable panes, and fewer decorative containers unless a
  modal or individual repeated item truly needs card framing.
- UI must look like a live recruiting marketplace/ATS/CV builder, not a
  prototype dashboard. Reviewers should reject screens that pass typecheck but
  still feel like generic SaaS cards without real hierarchy, workflow density,
  media, logos, rails, or task-specific controls.

## 4.1 Frontend Realism Rescue Bar

Use this bar whenever the UI feels "demo-like" or visually weaker than
`docs/DESIGN_EXAMPLE.png`.

- Public marketplace: enterprise top nav, company mega-menu, real brand/logo
  assets, campus/event media, overlay search, metric strip with honest deltas,
  public jobs left, employer/event/sponsored rail right, personalized or
  popular fallback recommendations, and trust rail.
- Public marketplace revenue/merchandising: use approved partner campaign
  creatives, VinUni-curated banners, strategic-partner spotlights, event/career
  day media, and right-rail/inline placements. Paid placements keep disclosure;
  curated/strategic content uses polished trust language.
- Floating action launcher: bottom-right desktop rail + mobile launcher for
  saved jobs, career opportunity invitations, messages, feedback/help, and
  VinUni AI when available. Buttons need hover/focus labels; AI may use a
  restrained pulse/glow with `prefers-reduced-motion`.
- Signed-in student: inherits marketplace-style top nav with student-specific
  items; no admin sidebar by default. First screen focuses on job discovery,
  active CV quota/readiness, recommended CV per job, applications, interviews,
  events, notifications, and AI nudges.
- CV Studio: feels like a document builder/template marketplace, not a profile
  form. Required composition: template shelf/library, upload/import, active CV
  quota, A4 preview, section/editor canvas, AI diff drawer, job-fit panel, export
  controls, version history, and mobile tabs.
- Partner: feels like a recruiting operations system. Required composition:
  company header with logo/trust/package, job health, candidate pipeline,
  interview/scorecard queues, team/RBAC, quota/package, ads/events, and activity.
- University: feels like an operations center. Required composition: moderation
  risk, partner requests, active partners/jobs/events/ads, notification/template
  health, AI/cost health, audit/security alerts, and clear SLA priorities.
- Visual rescue must include browser screenshots or inspection at 375, 768,
  1024, and 1440 and must update status as `functional-only`,
  `visual-design verified`, or `E2E verified` precisely.

## 5. Accessibility

- WCAG 2.1 AA minimum.
- Keyboard path for every interactive control.
- Visible focus for buttons, links, fields, tabs, menus, and drag/drop alternatives.
- Modals/drawers trap focus, close on Escape, restore focus on close, and block background scroll.
- Color is never the only signal.
- Respect `prefers-reduced-motion`.

## 5.1 Locale, Location, And Copy

- Support `vi` and `en` from day one.
- First visit may infer locale from browser language/coarse country; user preference always wins.
- User-facing date/time uses `Asia/Ho_Chi_Minh` by default and locale-aware formatting.
- Do not ask for exact location to personalize jobs; use profile career preferences and city-level filters.
- All notification/email/account/security copy must be i18n-backed, not hardcoded inside components.

## 6. Required UI Verification

For any non-trivial frontend feature, run:

- `pnpm type-check`
- `pnpm lint`
- `pnpm build`
- Browser or Playwright verification at 375px, 768px, 1024px, and 1440px.

For Visual/Product Rescue or any public homepage/dashboard redesign, capture or
inspect these routes at all four widths before completion:

- `/vi`
- `/vi/jobs`
- `/vi/companies`
- `/vi/student/dashboard`
- `/vi/partner/dashboard`
- `/vi/university/dashboard`

The reviewer must check: no horizontal overflow, no clipped text, real assets
load, sponsored labels remain visible, company logos use safe public URLs or
initials fallback, and persona dashboards do not share one generic composition.

For core workflows, add or run E2E covering:

- loading, empty, error, permission, and success states;
- mobile and desktop layouts;
- auth redirect and intent preservation;
- API contract payloads for writes.

## 7. Release Gate

A frontend feature is not complete until:

- build/lint/type-check pass;
- the real user path works against the backend contract;
- screenshots or browser inspection show no overlap, clipped text, or broken responsive layout;
- status docs distinguish `API wired`, `browser verified`, and `E2E verified`.

## 8. Required Settings Surfaces

Before Phase 1 is complete, the frontend must include:

- Account preferences: language, timezone, theme.
- Notification preferences: category/channel/digest/quiet hours.
- Security settings: active devices, remote logout, password, TOTP if enabled.
- Email/template admin screens for university admin when template management is in scope.

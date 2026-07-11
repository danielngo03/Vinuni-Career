# Partner + University UI Overhaul — Design Spec

> Date: 2026-07-09 · Branch: `feat/ui-overhaul` · Status: approved (brainstorming)
> Goal: rebuild the **partner** and **university** workspaces into a modern, data-rich
> admin/recruiting product on a **locked design system**, using real backend data,
> removing filler/hardcoded explainer content. Shell stays monochrome; content gets a
> real data-viz palette. This spec is the single source of truth every implementation
> agent builds against — do not deviate from the tokens, primitives, or IA here.

## 0. Non-negotiables (read first)
- **Real data only.** Every number, list, chart, and badge is fed by an existing (or
  newly-added) backend endpoint via the react-query hooks in `frontend/src/lib/api/*`.
  No hardcoded metrics, no lorem, no "this feature does X" explainer paragraphs, no
  fake screenshots. Honest empty/loading/permission states instead.
- **Shell monochrome, content colorful.** Header + sidebar stay black/white/gray (the
  approved shell). The content area uses the defined data-viz palette (§2) for charts,
  KPI tiles, category chips, and status.
- **One design system.** All surfaces reuse the Phase-0 primitives (§4). No bespoke
  one-off layouts. A surface = `PageHeader → KPI row → primary chart/table →
  secondary panels → activity`, with a right-edge `DetailSheet` for detail/edit.
- **Recruiter/admin POV.** Show what a real recruiter/university admin needs to act:
  fit %, pipeline health, SLA/aging, time-to-hire, source mix, competition, what-needs-
  attention — not vanity filler.
- **Accessibility + i18n.** Radix a11y kept; all copy in vi/en message catalogs
  (`pnpm check:messages` green); charts have text/table alternatives.

## 1. Foundation stack
- **Next.js App Router + Tailwind v4** (already). **Font: Plus Jakarta Sans** already
  the self-hosted default — do NOT re-add; instead enforce the locked type scale.
- **shadcn/ui (full adoption)** on Tailwind v4 + Radix. `npx shadcn init`, map tokens to
  our ink/gray ramp (light+dark) in `globals.css`. Generate: button, input, textarea,
  label, select, combobox, checkbox, radio, switch, slider, dialog, **sheet**,
  dropdown-menu, context-menu, **command**, popover, tabs, tooltip, table, badge,
  avatar, progress, separator, scroll-area, sonner (toast), skeleton, breadcrumb,
  pagination, calendar, chart. Migrate app usages off the hand-rolled `ui/*` where the
  shadcn version is better; keep our chart math only where it clearly beats Recharts.
- **Charts: Recharts** (via shadcn `chart`) + our existing sparkline/calendar-heatmap
  math where useful. **Icons: lucide-react ONLY** (remove the Phosphor mix in `nav.ts`).
- **Data tables: TanStack Table** + shadcn table shell. **Kanban:** dnd-kit (pipeline).
  **Flow builder:** React Flow (workflows). **Motion:** subtle, CSS/Tailwind first;
  framer-motion only for the Sheet/command transitions if needed.

## 2. Design tokens (add to `globals.css`; DESIGN.md §1.1.2 rewrite)
### Type scale (Plus Jakarta Sans; enforce, kill ad-hoc sizes)
`--text-display 30/36 600` · `--text-h1 24/32 600` · `--text-h2 20/28 600` ·
`--text-h3 16/24 600` · `--text-body 14/20 400` · `--text-small 13/18 400` ·
`--text-caption 12/16 500`. Metrics use `font-variant-numeric: tabular-nums`; big
metric = 28–32/600. Weights available: 400/500/600/700.
### Shell (unchanged, mono)
Header/sidebar backgrounds, borders, ink text from the existing gray ramp. No color.
### Content data-viz palette (NEW — light + dark tints)
Categorical (chart series / categories), in order: `indigo #6366f1`, `teal #14b8a6`,
`amber #f59e0b`, `rose #f43f5e`, `sky #0ea5e9`, `emerald #10b981`, `violet #8b5cf6`,
`orange #f97316`. Each gets a `-soft` bg tint (~12% alpha) for chips/tiles.
Semantic: success `emerald`, warning/sponsored `amber`, danger `VinUni red`, info/AI
`sky`/`indigo` (the current blue→gray remap is **reverted for content only**).
Hero stat card: ONE restrained gradient (indigo→violet) OR dark-ink card, used sparingly
for a top forecast/summary tile (à la Pipeline OS). Governed by the `dataviz` skill for
accessibility (contrast, light/dark, colorblind-safe ordering).

## 3. Information architecture (sidebar; lucide icons; grouped, no cramming)
### Partner
- OVERVIEW: Dashboard · Jobs
- HIRING: Candidates · Pipeline · Interviews · Offers · Talent Pool
- GROWTH: Analytics · Advertising · Events
- WORKSPACE: Team & Roles · Recruiting Workflows · Messages · AI Assistant · Security & Audit
- (Company profile, Billing, Settings → account/avatar menu or a Settings leaf)
### University
- OVERVIEW: Dashboard · Reports
- GOVERNANCE: Moderation · Partners · Users & Roles · Audit
- OPERATIONS: Career Services · Events · Reviews · Advertising · Messages
- INSTITUTION: Career Outcomes · CV Templates · Notification Templates · AI Settings · Subscriptions
- Workflow Builder · AI Assistant
Sidebar: collapsible, small-caps group titles, active/hover states, section counts where
real, ⌘K search in topbar, org switcher, notifications, avatar menu.

## 4. Phase-0 primitives (I build these first; agents ONLY consume them)
`AppShell` · `Sidebar` (grouped/collapsible) · `Topbar` (⌘K, quick actions, org switcher,
notifications, avatar) · `PageHeader` (breadcrumb+title+subtitle+meta+actions) ·
`DetailSheet` (right-edge drawer; header, scroll body, footer actions) · `DataTable`
(sortable/filterable/row-select/bulk-action/pagination/empty/loading) · `FilterBar` ·
`KpiTile`+`KpiRow` · `StatCard` (value + trend delta + sparkline) · chart wrappers
(`AreaChart`,`LineChart`,`MultiLineChart`,`BarChart`,`StackedBar`,`DonutChart`,
`RadialChart`,`Sparkline`,`CalendarHeatmap`,`FunnelChart`) · `ActivityFeed`/`Timeline` ·
`StatusChip` (semantic+categorical) · `CommandPalette` · `EmptyState` · `KanbanBoard`/
`KanbanCard` · `DrawerForm`. Each: typed props, light/dark, a11y, story-like exemplar
usage in the flagship screen. **Flagship exemplar = Partner Dashboard/Ops**, fully built
to lock the look; agents copy its structure.

## 5. Per-surface content (recruiter/admin POV; each with right-edge Sheet + modals)
- **Partner Dashboard/Ops:** KPI row (open jobs, active candidates, interviews this week,
  offers out, time-to-hire) → funnel + pipeline-health donut → job-performance table →
  ops/todo queue (the 7 actionable items) → team activity + access alerts. Gradient hero
  = weighted pipeline/forecast tile.
- **Jobs:** table + status chips + JD-quality gate; job detail Sheet (metrics, applicants,
  edit). **Candidates:** cross-job table w/ fit %, source, assignee, stage; candidate Sheet
  (CV, timeline, scorecards, reveal, offer). **Pipeline:** dnd Kanban w/ assignee, SLA aging,
  bulk move, rollback-reason, per-card evaluation. **Interviews:** scheduling hub/queue +
  calendar. **Offers:** approval + send queue. **Talent Pool:** masked blind-search cards +
  reveal-with-reason. **Analytics:** funnel, per-stage conversion, time-to-hire/in-stage,
  source attribution, per-job/per-campaign; date range + export. **Advertising:** campaign
  cards + delivery metrics (needs backend, §6). **Events:** manage + attendees. **Team &
  Roles:** members/roles/departments/invitations/ownership/audit (strong already — restyle).
  **Workflows:** React Flow canvas + right inspector. **Messages:** 3-pane inbox (Chatmo-style).
  **AI Assistant:** streaming chat surface.
- **University:** Dashboard (SLA/moderation/health), Reports, Moderation queue, Partners
  (approve/CRM), Users & Roles, Career Services (counselor workspace), Reviews, Advertising
  oversight, Career Outcomes, CV/Notification Templates, AI Settings (superadmin-masked),
  Subscriptions, Workflow Builder, Messages, AI Assistant.

## 6. Backend gaps to fill (only what the redesigned FE surfaces need)
- Recruiting **funnel + per-stage conversion + time-to-hire + time-in-stage** analytics
  read (WP3 partial; extend). **Campaign/ad performance** read (impressions/clicks/CTR/
  spend — missing). Wire **`Job.view_count`** (dead=0). **`GET /organizations/members/me`**
  capability map for UI gating. `ad.apply_start` attribution. Thin university dashboard/
  reports read-models. Each new endpoint: service-layer RBAC, audited if write, tests.

## 7. Execution & phasing
- **Phase 0 (me, sequential):** shadcn init + tokens + type scale + lucide standardize +
  all §4 primitives + AppShell/Sidebar/Topbar IA + flagship Partner Dashboard/Ops +
  DESIGN.md/CLAUDE.md/FRONTEND_DESIGN_PLUGIN_USAGE updates. Gate green. This LOCKS the look.
- **Phase 1 (parallel `frontend-developer` agents, partner):** partition disjoint surfaces
  (jobs/candidates/pipeline · interviews/offers/talent-pool · analytics/advertising/events ·
  team/workflows/messages/AI). `backend-developer` agents fill §6 gaps in parallel.
- **Phase 2 (parallel agents, university):** same partition on the locked system.
- Every phase: `code-review` + `security-review` + `code-simplifier` + tsc/build/
  check:messages + Playwright smoke. Isolated in `feat/ui-overhaul`; merge to
  `vinuni-main-submission`.

## 8. Acceptance
Per surface: real data wired (API/browser-verified), right-edge Sheet + relevant modals,
locked tokens/type/palette, lucide icons, honest empty/loading/permission states, vi/en
parity, a11y, no filler. Gates green. DESIGN.md updated so future work follows v10.

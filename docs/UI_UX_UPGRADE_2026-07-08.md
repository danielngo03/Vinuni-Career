# UI/UX System Upgrade — 2026-07-08

Branch: `feat/ui-system-upgrade` (based on `feat/ai-provider-model-admin`).
Scope: system-wide UI/UX audit + high-leverage refinement. The product was found
to be genuinely mature (real API data + honest states almost everywhere, real
queue-first dashboards via `dashboard-kit`), so this is **refinement, not rescue**:
one security fix, app-wide dark-theme correctness, the missing shared interaction
patterns, one fabricated metric removed, and a gradient/"AI-insight" consistency
sweep.

## What changed

### 1. Security — AI settings leak (fix)
`/university/ai-settings` and `/ai-settings/routing` rendered the real
provider/model/base-url/API-key registry (`AiProviderManager`) plus kill-switch /
rollout / budget governance to **any** university staff (no `SuperadminGuard`, and
the `aiSettings` nav item was the only `platform`-group item missing
`requiresSuperadmin`). Both pages are now `SuperadminGuard`-wrapped and the nav
item is gated — matching every sibling registry/ops surface. (CLAUDE.md AI-leakage
rule.)

### 2. Dark-theme correctness (app-wide)
The designed dark theme was broken on every overlay because shared primitives
hardcoded `white/*` + navy `rgba(11,34,57,…)` shadows. Re-tokenized:
`modal`, `sheet`, `tabs`, `select`, `toast`, `data-table`, `SkeletonCard`
(`bg-white/8x → --surface-card`, `border-white/{40,60} → --border-{subtle,default}`,
`hover:bg-white/60 → --surface-hover`, navy shadows → `--shadow-*`). Fixed a real
dark contrast bug in the selected `Tab` (`bg-[--brand-primary] text-white` →
theme-aware `--btn-primary-bg/fg`). Tokenized the hardcoded `#f7f6f2` ops/full-canvas
surface as a new `--ops-canvas` token (light + dark) across shell + settings +
notifications + messaging; topbar sticky header → `--surface-overlay`.

### 3. Shared interaction primitives (new, `components/ui/`)
The patterns the app was hand-rolling per screen, all tokenized / accessible /
dark-safe: `ListToolbar` + `SearchInput` + `FilterChip`, `ViewToggle`, `Checkbox`
(indeterminate), `useRowSelection` + `BulkActionBar`, `ExportButton`,
`DataFreshness` (fresh/stale/unavailable), `InsightPanel` (flat monochrome "signals"
to replace gradient AI-styled heuristic cards). Exported from the `ui` barrel.

### 4. Dashboard / screen realism
- **Student dashboard:** removed a fabricated hero metric (a card rendering the
  literal string `"CV Studio"` as the CV count) + redundant welcome copy, dropped
  the navy/gradient hero → flat monochrome command-center header. Real numbers were
  already in the MetricTiles below.
- **Student applications:** de-glassed tiles + cards, replaced the gradient "AI"
  panel with `InsightPanel`, and added a `ListToolbar` (search + status FilterChips
  with live counts + result count + honest no-match state). Exercises every new
  primitive.

### 5. Consistency sweep (de-gaudy) — 8 more screens
Replaced gradient "AI insight" panels (client-side heuristics mislabeled with a
Sparkle/AI affordance) with the honest `InsightPanel`, and normalized glass surfaces
+ raw Tailwind palette colors + navy shadows + `text-white`-on-icon-chip → v9 tokens:
student `saved-jobs / student-events / job-alerts / student-invitations`; partner/uni
`partner-dashboard / university-dashboard / partner-analytics / talent-pool`.
`partner-dashboard-ops` intentionally kept its AI treatment — it renders a **real**
backend `ai_recommendations` contract, not a heuristic.

### 6. Cleanup
Deleted two unimported orphan duplicate files (`* (1).tsx`). Added reusable
`common.results / noResultsTitle / noResultsBody / clearFilters` (en + vi).

## Verification (commands run in this worktree)
- `pnpm typecheck` → **pass** (exit 0)
- `pnpm lint` → **pass** (exit 0; 2 pre-existing warnings only — `public-job-board`
  + `notification-screen` useMemo deps, both pre-existing per CLAUDE.md, untouched)
- `pnpm build` → **pass** (full route manifest emitted)
- `node scripts/check-message-parity.mjs` → **pass** (51 files, en/vi in sync)
- Browser (Playwright, production build on :3177, no backend): public marketplace
  `/vi` at **1440** and **375**, forced dark theme — dark surfaces render correctly
  (no milky-white overlays), tokenized error/empty state + nav + search + filter
  chips are dark-safe, **no horizontal overflow at 375** (scrollWidth 360 ≤ 375).

### Status labels (per UI_QUALITY_BAR)
- **API wired + static-gate verified (typecheck/lint/build):** all changes.
- **browser verified:** public marketplace dark theme + 375/1440 responsive only.
- **NOT browser verified:** authenticated dashboards/applications (need a live
  backend session — recommend a QA pass at 375/768/1024/1440 in light + dark).

## Backend read-model follow-ups (proposed backlog — IDs continue from B-603)
Recorded here rather than in `docs/BACKLOG.md` to avoid ID collision (this branch's
BACKLOG base predates the main checkout's uncommitted B-579…B-603).

- **B-604 (P1):** Student dashboard data completeness — expose CV-readiness/quota and
  offers count in the dashboard read model so the header can show them as first-class
  tiles (today only applications/cv_count/alerts exist).
- **B-605 (P1):** Partner candidates bulk actions — bulk stage-move / reject / reveal
  (real endpoints or audited client-side fan-out over existing per-item mutations)
  + fix the 3-ghost-button row-action overflow at 768–1024 (overflow menu). Reuse
  `useRowSelection` + `BulkActionBar`.
- **B-606 (P1):** Moderation SLA/reason parity — `reviews-moderation` and
  `abuse-triage` need the same `SlaBadge` + `ReasonCodeSelect` + bulk primitives and
  read-model fields (due_by, age, reason codes) as job/event moderation.
- **B-607 (P2):** Partner analytics — real charting + server-side date-range filter +
  export (today CSS-bar charts, no date range). Needs an analytics read model with
  range params.
- **B-608 (P2):** Admin user tables (`university-users`, `access`) — bulk role/suspend
  + export.
- **B-609 (P2):** Charts dark-theme — `charts/chart-theme.ts` hardcodes 31 hex values
  (light-only); read CSS variables / accept a resolved theme.
- **B-610 (P3):** `career-explore` public destination dead-ends into a placeholder —
  build the real discovery surface or point the nav item at a live surface.
- **B-611 (P3):** Icon-library normalization — the isolated `lucide-react` nav/layout
  + notifications layer (14 files) renders a different stroke weight than the
  phosphor-based rest of the app; migrate to one library.

## Notes / residual risks
- Some `InsightPanel` titles still read "…Insights"/"AI" in their i18n **value**
  (key unchanged) — the gradient/Sparkle AI *styling* was removed (the honesty fix);
  a copy pass could rename the few that literally say "AI".
- The branch includes a first commit that snapshots pre-existing uncommitted
  working-tree WIP (marketplace-nav, CV builder, layout, jobs helpers) as a baseline
  so the upgrade diff stays reviewable; it is **not** part of this upgrade.

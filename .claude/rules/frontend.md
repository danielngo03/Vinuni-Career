---
description: Frontend implementation, visual quality, accessibility, i18n, and browser QA rules.
paths:
  - frontend/**
  - docs/DESIGN.md
  - docs/UI_QUALITY_BAR.md
  - docs/SCREEN_SPECS.md
  - docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md
---

# Frontend Rules

Use for Next.js UI implementation, review, polish, responsive behavior, i18n,
and browser verification.

## Must Read

- `CLAUDE.md`
- `docs/PRODUCT_REQUIREMENTS.md` for the touched persona/workflow
- `docs/PRODUCT_REALITY_REBUILD_SPEC.md` for practical, non-demo workflow checks
- `docs/DESIGN.md`
- `docs/UI_QUALITY_BAR.md`
- `docs/SCREEN_SPECS.md`
- `docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md`
- `docs/API_CONTRACTS.md`
- `docs/SECURITY_PRIVACY.md`
- `docs/EDGE_CASES_FAILURE_MODES.md`
- `docs/SYSTEM_ACCEPTANCE_BAR.md`
- Feature-specific specs such as `docs/CV_STUDIO_SPEC.md`,
  `docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`,
  `docs/PARTNER_RBAC_ANALYTICS_SPEC.md`, and
  `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`.

## Visual Direction

- Follow **v10 "Monochrome Shell + Data-viz Content"** (`docs/DESIGN.md §1.1.2`):
  the SHELL (header, sidebar) stays premium black/white/gray with ink as the only
  action color; the CONTENT area uses the defined data-viz palette (`--viz-*` +
  `-soft` tints; `--content-{success,warning,danger,info,ai}`) for charts, KPI
  tiles, category chips, and status. The blue→gray remap is reverted for CONTENT
  only (sky/indigo for info + AI + primary data series); the shell ramp is mono.
- Colour is for meaning and data density, not decoration. Chart series, KPI
  deltas, status chips, and category tags may be colourful; page chrome may not.
- Exactly ONE restrained gradient is allowed: the `--hero-gradient` (calm brand
  BLUE — NO purple/violet/indigo) forecast/summary hero card, used sparingly
  (≤1 per surface). Violet is a chart-series colour only, never a hero/UI accent
  (owner, 2026-07-10).
  No decorative blobs/orbs, no emoji icons, no fake screenshots, no marketing filler.
- Build on the locked design system: shadcn/ui primitives in `@/components/ui`
  and the shared kit in `@/components/kit` (Card, PageHeader, KpiTile/KpiRow,
  GradientHeroCard, StatusChip, DetailSheet, DataTable, CommandPalette, charts,
  ActivityFeed, AttentionPanel, FilterBar). Do NOT hand-roll one-off equivalents.
- Icons: **lucide-react only** (no Phosphor). Type scale is locked
  (`.type-display/h1/h2/h3/body/small/caption/metric` + `tabular-nums` for
  metrics) — never set ad-hoc font sizes.
- Use stable dimensions for navigation, filters, cards, toolbars, boards, tables,
  canvases, and preview panes.
- Typography must fit the container at desktop and mobile sizes. Do not scale
  font size directly with viewport width.
- Hover, active, selected, disabled, loading, error, and focus states must be
  deliberately designed and consistent across the product.

## Product UX Rules

- Public and student experiences use a top navigation marketplace model.
  Partner and university experiences use operating shells with sidebar/topbar.
- Do not create generic dashboards. Each persona needs real queues, next
  actions, alerts, recent activity, and deep links into actual workflows.
- Do not label a list as recommended unless the backend returns a real
  recommendation contract, reason codes, or an explicit fallback source such as
  recent/popular.
- Sponsored jobs, events, employers, and banners must be visibly disclosed and
  separated from organic/recommended inventory.
- Guest actions that require authentication open login/register and preserve
  the original intent.

## CV Studio Rules

- CV Studio is a visual document product, not a profile-form product.
- The primary CV creation flow is: upload existing CV, choose a template,
  duplicate a CV, or ask AI to draft/fill a template. Never require students to
  complete long education/experience/profile forms before CV creation.
- The builder must feel like a Canva/document editor: template gallery, A4
  canvas preview, inline text editing, section/block selection, drag/drop,
  photo replace/crop, style tokens, page-break warnings, undo/redo, autosave,
  and export preview.
- Side panels/inspectors may edit metadata, layout, and selected block options;
  they must not become the primary long-form editing experience.
- AI editing uses a natural-language command bar and returns a visible diff or
  patch. The student must accept, edit, or reject before any CV mutation.
- University template management must support preview, validation, versioning,
  draft/publish/archive, and ownership metadata.

## Auth And Forms

- Forms are appropriate for authentication, settings, admin configuration, and
  small metadata edits. They are not the primary UX for CV authoring.
- Inputs must have one visible field boundary. Focus state should preserve
  radius and use a polished ring/shadow, not a harsh double border.
- Validation errors appear near the relevant label/control and should not cause
  layout jumps.
- OTP, password reset, verification, and onboarding screens must have clear
  back navigation, resend state, rate-limit state, expiry state, and safe
  non-enumerating copy.

## Data And AI Safety

- Never expose provider names, concrete model ids/model names, prompts, token
  counts, raw confidence, embeddings, storage keys, raw object paths, or
  internal error codes to students, partners, guests, ordinary university staff,
  exports, or notifications. Only superadmin AI operations/settings screens may
  render real provider/model registry details; all other AI UI is alias/status
  masked.
- AI suggestions are advisory unless paired with explicit confirmation.
- Permission and privacy states must be visible in the UI, but backend service
  checks remain final.
- Do not fake metrics. Use real API data, skeletons, honest empty states, or
  permission-disabled states.

## Verification

- Check desktop and mobile breakpoints at minimum: 375, 768, 1024, 1440.
- Verify light and dark themes when the touched surface supports theme.
- Verify keyboard focus order, tab stops, Escape/Enter behavior, and screen
  reader labels for menus, dialogs, tabs, filters, and canvas toolbars.
- Before marking a UI slice done, record whether it is `API wired`,
  `browser verified`, and `E2E verified`.

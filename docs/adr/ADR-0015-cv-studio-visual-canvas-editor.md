# ADR-0015: CV Studio Visual Canvas Editor — Rendering Unification, Template Binding Schema, Migration

**Status:** Proposed
**Date:** 2026-07-04
**Module:** `documents` — `backend/app/modules/documents/`, `frontend/src/components/cv/`
**Backlog:** B-528 (this ADR breaks it into B-528.1..5 — see suggested BACKLOG.md update in the handoff)

## Context

Product-reality audit finding: CV Studio's editor is a textarea-per-section form
(`cv-builder-screen.tsx`, `cv-section-editor.tsx`) with a **read-only mirror**
preview (`cv-a4-preview.tsx`) that independently re-renders `sections` with its
own heuristics (a second, drifting "page estimate" line-count formula). This
violates `CV_STUDIO_SPEC.md` "Visual Canvas Editor Contract": no inline editing
on the canvas, no block selection, no drag/drop of visual position (only
section-level array reorder), no style controls, and — critically — **the
export PDF (`pdf_render.render_cv_pdf`) is a fully independent third render
path** that reads only `snapshot_json.sections` and ignores `canvas_json`
entirely (no block order/position, no photo, no style). Three divergent
renderers for one document is the core defect, not just "the editor looks like
a form."

Non-obvious finding from code inspection: the backend is **further along than
the audit assumed**. `cv_profiles.canvas_json` already exists, versioned and
audited, with a working `PATCH /cvs/{cv_id}/canvas` (`cv_canvas_service.py`,
allowlisted block types `text|list|heading|image|divider|spacer|custom`,
`order`, `visible`, `style` dict) and a working photo replace/crop/remove
service (`cv_photo_service.py`, normalized 0..1 crop rect, shape enum). **None
of this is consumed by the frontend at all** — grep confirms zero references to
`canvas_json`/`canvas` in `frontend/src/`. So this is not "build the canvas data
model from scratch"; it is "build the canvas UI against an existing,
underused backend contract, and make export/preview use it."

Separately, `docs/DATA_MODEL.md` already specifies `content_binding_schema`,
`cv_template_versions`, and `cv_template_assets` for `cv_templates` — the ORM
(`domain/models.py::CvTemplate`) implements **only** `layout_schema` and a dead
`preview_image` column (nothing writes to it; `template_admin_service.py` has no
publish/version/render path). The doc is correct; the code is the stale side.

## Decision

### 1. One render pipeline, three consumers

Introduce a single backend-owned **CV render function** —
`documents.infrastructure.cv_render.render_cv(snapshot_json, canvas_json,
template_layout_schema, *, mode: "screen" | "export" | "thumbnail",
watermark=None) -> RenderDocument` — where `RenderDocument` is an intermediate,
serializable tree of positioned page/block nodes (page size, block rects,
resolved typography/style tokens, resolved text/list content, resolved photo
crop). This intermediate representation, not raw JSON, is what every consumer
renders from:

- **On-screen canvas/preview** (frontend): fetches `RenderDocument` via a new
  `GET /api/v1/cvs/{cv_id}/render?mode=screen` (or embeds it in the existing
  `GET /cvs/{cv_id}` detail payload as `render_tree`) and paints it as DOM
  (see §2 for why DOM, not canvas/SVG).
- **PDF export** (`export_service.py`): calls the same `render_cv(...,
  mode="export")` and feeds the resulting `RenderDocument` to a new
  `pdf_render.render_document(doc: RenderDocument, watermark=None)` — replacing
  today's `render_cv_pdf(snapshot_json)` which reads raw JSON directly. `fpdf2`
  stays (lightweight, no system deps per `LOCAL_DEV_STACK.md`), but it becomes a
  **pure `RenderDocument` → bytes** renderer, not a CV-shape-aware one.
  Positioning must be computed once in `render_cv`, not re-derived by fpdf.
- **`preview_image` thumbnail** (templates): `render_cv` called with a sample
  snapshot (`template.sample_content` — see §3) at `mode="thumbnail"`, piped to
  a raster export (reuse the same PDF path + a page-to-PNG step using a
  lightweight pure-Python rasterizer already reachable from `fpdf2`'s output, or
  — if quality is inadequate — `pypdfium2` for PDF→PNG; both are pip-only, no
  system binaries, consistent with `LOCAL_DEV_STACK.md`'s no-Docker-runtime,
  lightweight-dependency default). This runs server-side, never client-side
  canvas-to-image (client screenshots are not print-accurate and would
  reintroduce a second visual truth).

This directly satisfies the spec line "Export preview uses the same render
pipeline as generated PDF" by construction: there is exactly one geometry/style
resolution step, and every output format is a projection of it.

### 2. Canvas rendering approach: DOM + CSS, not `<canvas>`/SVG/PDF.js

**Recommendation: server-resolved `RenderDocument` painted as absolutely
positioned DOM blocks inside a fixed-aspect-ratio A4 container**, using
`transform: scale()` for zoom/responsive fit (same technique already used by
`cv-a4-preview.tsx`'s `aspectRatio` box, extended from a passive mirror to the
live editable surface).

Rejected alternatives and why:

- **HTML5 `<canvas>` (Konva/Fabric.js) or SVG canvas**: gives precise
  pixel/vector control and easy drag/resize handles, but forces the team to
  reimplement text layout, IME/Vietnamese diacritic input, accessibility (no
  semantic HTML — `CV_STUDIO_SPEC.md` §10 requires "editor text remains
  semantic HTML"), copy/paste, and screen-reader support from scratch. This is
  a hard "no" given the explicit accessibility contract.
- **Full PDF.js render-and-overlay**: real print accuracy but read-only by
  nature; editing would still need a separate DOM layer, so this only helps the
  final preview step, not authoring. Reserve as an option for a later "exact
  export preview" toggle, not the canvas itself.
- **DOM/CSS with `contentEditable` regions per block**: matches
  `dnd-kit`(already the project's chosen DnD runtime per `DESIGN.md`, already
  used for section reordering in `cv-builder-screen.tsx`), keeps text as real
  HTML for accessibility, and lets the *same* layout math (block rect + style
  tokens from `RenderDocument`) be expressed as CSS (`position: absolute; left;
  top; width; height` inside a `210mm x 297mm` container at a fixed DPI
  constant, scaled via CSS `transform` for viewport fit) that the backend also
  uses to compute PDF coordinates. This is the only option that satisfies both
  "inline text editing on canvas" and "same pipeline as export" without a
  second full layout engine. **No new heavyweight canvas library dependency is
  required** — `@dnd-kit/core` (already a project dependency per `DESIGN.md`
  §package table) covers drag/reorder and free-ish positioning (constrained to
  a grid/snap, not arbitrary pixel dragging in V1 — see open question #2).

Contract: the frontend never invents block geometry. It requests
`RenderDocument`, renders it, and any position/size the student changes is sent
back as a canvas mutation (`PATCH .../canvas`) using the same block-id/order/
style vocabulary the backend already validates in `cv_canvas_service.py`
(extended per §3).

### 3. Data model changes

**a. `content_binding_schema` (fixes the "field doesn't exist" gap).** Add to
`CvTemplate` (and mirror in a new `CvTemplateVersion` table — see (c)):

```json
{
  "bindings": [
    {
      "block_id": "hdr_name",
      "source": { "kind": "field", "path": "profile.full_name" },
      "fallback": { "kind": "literal", "value": "" },
      "max_lines": 1,
      "overflow": "truncate_ellipsis"
    },
    {
      "block_id": "sec_experience",
      "source": { "kind": "section", "section_type": "experience" },
      "repeat": { "item_template_block_id": "exp_item", "max_items": 6 },
      "overflow": "new_page"
    }
  ],
  "photo_block_id": "hdr_photo",
  "locale_fallback": { "vi": "en", "en": "vi" }
}
```

`source.kind` is one of `field` (a scalar CV fact — name/email/phone/summary),
`section` (binds to a `cv_sections.section_type`, one-to-many via `repeat`), or
`static` (template-owned decorative text, never student content). This is the
minimum vocabulary needed to satisfy spec requirements: "repeatable section
rules, fallbacks, max lines, and overflow behavior." Rendering (`render_cv`)
resolves bindings against the CV's sections/profile fields to produce the block
content that then gets positioned per `layout_schema`.

**b. `preview_image` generation trigger.** Server-side render job, **not**
client snapshot (client canvas screenshots are not print-accurate and would
resurrect the two-render-path problem this ADR eliminates). Trigger points:
template draft save (debounced, on any `layout_schema`/`content_binding_schema`
change) and explicit `POST /admin/cv-templates/{id}/preview` (already in the
spec's API list, currently a no-op path in `template_admin_service.py` per the
audit — must actually call `render_cv(..., mode="thumbnail")` against
`template.sample_content` and write the resulting storage key to
`preview_image`). This is synchronous-acceptable for V1 (small A4 render, not a
heavy job) but must go through the same Celery-eligible boundary as exports so
it can be moved to async without an API change if render cost grows.

**c. Template versioning/publish/archive** (currently entirely missing from
the ORM despite being in `DATA_MODEL.md` and the spec's "University template
operations"). Add `CvTemplateVersion` (`template_id`, `version_number`,
`layout_schema`, `content_binding_schema`, `preview_image`, `status`
draft/published/archived, `created_by`, `published_at`) exactly as
`DATA_MODEL.md` §"cv_template_versions" already specifies. `CvProfile` must
gain `template_version_id` (nullable FK) recorded **at creation/export time** —
this is the mechanism that satisfies "Publish/archive a version without
breaking existing student CVs": a CV always renders against the
layout/binding-schema version it was created with, never the template's
currently-published head, unless the student explicitly opts into
"Update to latest template version" (a new, explicit, diffable action — not a
silent migration).

**d. `sample_content`.** New `CvTemplate.sample_content: JSONB` — a
university-authored placeholder CV snapshot (fake name/sections) used purely to
render the marketplace thumbnail and the in-builder "preview this template"
state before any student content exists. Never real student data.

### 4. Component architecture (frontend)

New components under `frontend/src/components/cv/canvas/`:

- `CvCanvasRoot` — fetches `render_tree` + `canvas_json`, owns the A4 container
  (fixed mm-based coordinate system, CSS `transform: scale()` for zoom/mobile),
  keyboard focus management, undo/redo stack (client-side command log that
  replays as canvas/section PATCH calls — see below).
- `CvCanvasBlock` — one positioned block; renders semantic HTML
  (`h1`/`p`/`ul`/`img`) per `block.type`, is `contentEditable` for text/list/
  heading types, becomes "selected" (inspector-visible) on click/focus.
- `CvCanvasInspector` — right-rail panel for the selected block: typography
  (size/weight/align), spacing, visibility toggle, section metadata — **this is
  the existing "compact inspector" from the spec, not a replacement for the
  canvas**.
  the canvas.
- `CvCanvasDragLayer` — thin wrapper around the project's existing
  `@dnd-kit/core` + `@dnd-kit/sortable` usage (already present for section
  reorder in `cv-builder-screen.tsx`), extended to reorder/move blocks within
  and across sections; keyboard-move fallback (arrow keys while a block is
  focused) is mandatory per spec §10 and per `frontend.md`.
- `CvPhotoCropDialog` — wraps the existing `cv_photo_service` contract
  (upload/replace/crop rect/shape/remove); a modal, not inline canvas
  manipulation, for V1 (dragging a live crop handle on-canvas is a
  fast-follow, not required to ship the first usable version).
- `useCvCanvas` hook — single source of truth for `sections` + `canvas_json` in
  the builder, replacing the current bespoke `sections`/`sectionsRef` state in
  `cv-builder-screen.tsx`. **Must preserve, not rebuild**: the existing
  autosave debounce/queue (`enqueue`, `scheduleAutosave`, optimistic
  `expected_version` conflict handling), version-restore
  (`CvVersionCard`/`restoreVersion`), and the AI-diff flow
  (`CvAiAssistCard`, `cv_ai_service.py`'s pending-suggestion pattern) exactly
  as-is — the canvas only changes *how content is edited and positioned*, not
  how saves/versions/AI-diffs work. AI-produced diffs continue to target
  `cv_sections` content; the canvas layer is presentation and is versioned
  alongside content in the same `cv_versions` snapshot (already true today via
  `canvas_json` inclusion — confirmed in `cv_canvas_service.py` comments).

### 5. Migration plan (no data loss for in-progress CVs)

Every existing `cv_profiles` row already has `canvas_json = {}` (its declared
default) because the frontend never wrote to it. Migration is therefore
**additive, not transformative**:

1. Ship a **default canvas synthesizer**: when the builder opens a CV whose
   `canvas_json.blocks` is empty/missing, the backend (`_cv_core` or a new
   `_cv_core._synthesize_default_canvas`) generates one block per visible
   section in existing `sort_order`, plus a header block for
   title/contact, using the CV's `template_id` layout (or a generic single-
   column fallback layout if no template). This is computed on read, not
   backfilled via migration — avoids a risky bulk data migration and means a
   CV opened once in the new editor gets a canvas that matches exactly what it
   looked like in the old textarea/A4-mirror rendering, then the student edits
   forward from there.
2. Templates: existing `cv_templates` rows get `content_binding_schema = {}`
   default (already the DB default per `DATA_MODEL.md`) and a migration script
   seeds bindings for the platform-seed templates only (`template_seed.py`) —
   university-created templates in `draft` status are unaffected until a
   university admin republishes with the new schema. Templates without bindings
   fall back to the section-dump layout (today's behavior) — **never a hard
   failure**.
   3. No `cv_profiles.template_version_id` backfill is destructive: NULL means
   "rendered against the template's current head" (today's implicit behavior),
   preserving existing CVs' visual output exactly.
4. Old `cv-a4-preview.tsx` heuristic page-break estimate is deleted once
   `RenderDocument` provides a real overflow signal from `render_cv` (per-block
   `overflow` resolution from the binding schema) — this removes the
   "drifting second formula" defect identified in Context.

### 6. Sequencing (5 slices, dependency order, each independently shippable)

1. **Data model + binding schema + versioning + migration.**
   `content_binding_schema` on `CvTemplate`, new `CvTemplateVersion`,
   `CvTemplate.sample_content`, `CvProfile.template_version_id`, default-canvas
   synthesizer, Alembic migration (up/down). *Acceptance: an existing seeded CV
   with `canvas_json={}` opens and a synthesized canvas with correct block
   count/order is returned by `GET /cvs/{id}` without any manual data fix.*
2. **`render_cv` unification + `RenderDocument` + read-only canvas shell.**
   Backend `render_cv()` intermediate representation; frontend `CvCanvasRoot`/
   `CvCanvasBlock` render it read-only (no editing yet), replacing
   `cv-a4-preview.tsx`; export switches to `render_document` (still same visual
   output as today, now from one pipeline). *Acceptance: exported PDF and
   on-screen preview are pixel-equivalent for a fixed test CV (same section
   order/content), verified by rendering both and diffing computed block
   rects.*
3. **Inline editing + block selection + drag/drop.**
   `contentEditable` blocks wired to existing section-content mutation calls;
   `CvCanvasInspector` (typography/spacing/visibility); drag/drop reorder via
   `@dnd-kit` extended to blocks; keyboard move fallback. *Acceptance: editing
   a bullet inline on the canvas persists via the existing autosave path and
   round-trips through version restore identically to the old textarea flow.*
4. **Photo replace/crop + style controls + template switch preview.**
   `CvPhotoCropDialog` wired to `cv_photo_service`; style token controls
   (font/color/spacing presets, not arbitrary CSS) exposed in the inspector;
   switching template re-resolves bindings and shows a diff/preview before
   applying. *Acceptance: replacing a photo with a crop persists, appears
   identically in on-screen canvas and exported PDF.*
5. **Template admin: publish/archive/preview + `preview_image` generation +
   mobile canvas mode.** `template_admin_service.py` publish/archive endpoints
   write real `CvTemplateVersion` rows; `POST .../preview` actually renders and
   sets `preview_image`; mobile Sections/Edit/Preview/AI tabs use the same
   `RenderDocument` at a scaled-down read/edit mode per spec §9. *Acceptance: a
   university admin publishing a new template version does not change the
   rendered output of any CV created against the prior version.*

## Consequences

+ Single render truth eliminates the three-divergent-renderer defect and makes
  "export preview equals export" true by construction, not by convention.
+ Backend canvas/photo infrastructure that already exists and is tested gets
  used instead of rebuilt — meaningfully smaller implementation surface than
  the audit's framing suggested.
+ DOM/CSS approach keeps accessibility, Vietnamese IME input, and the existing
  `@dnd-kit` investment; no new heavyweight canvas library dependency.
− Slice 2 requires computing PDF geometry in Python from the same
  `layout_schema`/`content_binding_schema` the frontend uses in CSS — two
  independent implementations of "the same layout math" in two languages is an
  ongoing consistency risk (mitigated by slice 2's pixel-equivalence test
  becoming a permanent regression test, not a one-time check).
− Free-form pixel dragging is descoped to grid/slot-constrained positioning in
  V1 (open question #2) — some "Canva-like" flexibility is deferred.

## Alternatives rejected

- **Canvas/SVG library (Konva/Fabric.js) as the editing surface** — rejected
  for accessibility/semantic-HTML and IME/text-editing reasons (§2).
- **Keep two render paths but add visual polish only to the on-screen editor**
  — rejected; this is exactly the defect the audit flagged and would make the
  divergence worse (screen would show block positions/photo that PDF export
  still ignores).
- **Client-side canvas screenshot for `preview_image`** — rejected; not
  print-accurate, reintroduces a third render source.
- **Bulk-migrate all existing CVs' canvas_json via a data migration** —
  rejected in favor of on-read synthesis; safer for in-progress student CVs
  (no destructive bulk JSON transform against production data).

## Required doc updates at implementation time

`docs/DATA_MODEL.md` (add `CvTemplateVersion`/`sample_content`/
`template_version_id` — mostly already present, reconcile ORM-vs-doc drift
noted in Context); `docs/API_CONTRACTS.md` (new `GET /cvs/{cv_id}/render`,
document `content_binding_schema` shape in the template admin endpoints,
document `POST /admin/cv-templates/{id}/preview` actual behavior);
`docs/CV_STUDIO_SPEC.md` (no scope change expected, but confirm the binding
vocabulary in §3 matches this ADR once implemented); `docs/BACKLOG.md` /
`docs/IMPLEMENTATION_STATUS.md` (orchestrator applies the B-528 breakdown from
the handoff, not this agent).

## Open questions for `product-owner-system-planner` sign-off

1. **V1 "style controls" scope** — this ADR assumes a **constrained token
   picker** (a small set of university-approved font/color/spacing presets per
   template), not a free-form rich-text/CSS editor. Confirm this matches
   product intent before slice 4, since "arbitrary styling" would reopen the
   canvas-library question in §2.
2. **Free-form vs. grid-constrained block positioning** — this ADR recommends
   grid/slot-constrained drag positioning for V1 (blocks snap to
   template-defined slots/columns) rather than arbitrary-pixel free placement,
   to keep `layout_schema` tractable and keep PDF-geometry parity (Consequences
   note above) achievable. Confirm whether "true Canva-like free placement" is
   a hard V1 requirement or acceptable as a later phase.
3. **`pypdfium2` (or equivalent) as a new dependency** for `preview_image`
   PNG rasterization — falls under "lightweight dependency" per
   `LOCAL_DEV_STACK.md` (pip-only, no system binary) but is a new third-party
   dependency; confirm acceptable under Plugin Policy / dependency review
   norms, or propose an alternative rasterization approach.
4. **Template "update to latest version" UX** — confirmed as an explicit,
   diffable, student-triggered action in this ADR (never silent); needs a
   one-line product decision on whether it's available in V1 or deferred
   entirely (a template version bump with no re-sync path is also acceptable
   for slice 5).

# CV Builder — Canva-feel + Customization Redesign (Design Spec)

Date: 2026-07-05 · Owner-approved (Hướng A). Builds on P1/P2 (`<CvDocument/>` renderer, canvas
editor) and the CV library lifecycle spec.

## Owner intent

Make the template CV builder feel like a real modern recruitment-system / Canva editor:
diverse templates **with icons**, rich text styling, **customization** (add fields the template
lacks — e.g. Facebook/GitHub/LinkedIn), a **proper AI chat assistant** (not a dead card / a
floating button), a proper version history, and modern layout. Keep the **structured** document
model (Hướng A) — matching reads structure directly; do NOT rebuild on a free-canvas library.

Explicit owner points:
- The current "Trợ lý AI" static card + bottom-corner floating AI button feel meaningless →
  replace with an integrated AI chat panel (the AI backend already exists: request→pending
  diff→accept/reject→version, non-destructive).
- Templates must carry **contact icons** (phone/email/location/social).
- Customization: if a template's personal-info block has no LinkedIn/GitHub/Facebook field, the
  student must be able to **add it** (typed links + custom fields/items).
- **Finalize ("Lưu vào thư viện CV") runs an analysis/extraction step** so a committed CV is
  prepared for matching — conceptually "like upload extraction" (owner mental model). For a
  structured builder CV this is a deterministic derive/normalize (NO OCR/vision — the data is
  already structured), with the AI-enrichment seam kept for later. Show "Đang phân tích CV…".
- Drag-drop is nice-to-have, not mandatory.

## Data contracts (both agents build to these)

1. **Per-element style overrides** — for the contextual text toolbar. Stored in
   `canvas_json.elementStyles = { [editPath]: ElementStyle }` where `editPath` is the same
   `data-edit-path` grammar from P2 and `ElementStyle = { font?: fontToken, size?: 'xs'|'sm'|'base'|'lg'|'xl'|'2xl', weight?: 'normal'|'medium'|'semibold'|'bold', italic?: bool, align?: 'left'|'center'|'right', color?: '#hex' }`.
   Backend validates against allowlists (reuse `themes` font tokens + a size/weight/align enum +
   hex regex); unknown keys stripped; empty resets. Applied by the renderer per text node on top
   of the theme. Written via the existing `PATCH /cvs/{id}/canvas` (sibling of `theme`).
2. **Typed contact links** — header links become `{ label, url, type? }` where `type ∈
   email|phone|website|linkedin|github|facebook|twitter|instagram|custom`. Renderer maps `type`
   (and email/phone/location) to an icon. Backend accepts/persists `type` in the header section
   content; unknown types → `custom`.
3. **Finalize analysis** — implement `cv_lifecycle_service._analyze_for_matching(cv, sections)`
   to derive + store a matching representation (normalized skills, keywords, contact,
   experience span) deterministically from the structured sections (no OCR/AI tokens). Store on
   the CV (e.g. `matching_json` column or reuse an existing field). Finalize stays: validate
   non-empty → quota → analyze → status ready → version + audit. Idempotent when ready.

## Frontend — builder UX (the visible redesign)

Layout (desktop): left = section outline (keep); center = A4 canvas (keep, add icons + per-element
styling + inline edit); right = a **clean tabbed inspector**:
- **Thiết kế / Design** — template gallery, palette + accent, font pairing, density (current Restyle).
- **Phần tử / Elements** — insert: **typed social link + icon** (LinkedIn/GitHub/Facebook/website/custom),
  custom field, divider, skill bar, and add-section. This is the "customization" surface.
- **AI** — the **AI chat assistant**: a message input + intent chips (rewrite / optimize for role /
  ATS keywords / fill from profile / evidence-check). Sends via the existing
  `requestAiEditCommand` / task suggestion endpoints → shows the returned **pending diff** as a
  preview → Accept (fact-confirm when required) / Reject → applied + versioned. Non-destructive.
- **Phiên bản / Versions** — a proper history: timeline, timestamp, change summary, Restore
  (existing `restoreVersion`), current-version marker.

**Contextual text toolbar (Canva signature):** selecting/focusing a text element shows a floating
toolbar near it: **Font · Size · Bold/Italic · Color · Align**. Writes to `elementStyles[editPath]`
via the canvas PATCH (optimistic + autosave, versioned).

**Contact icons:** header renders email/phone/location icons + a per-link icon by `type`. Uses the
project phosphor icon set; monochrome-consistent (icons inherit theme ink/muted, not rainbow).

Remove: the static `CvAiAssistCard` and the floating bottom-corner AI button (fold into the AI tab).
Keep `DocumentHealthCard`/`CvJobFitRail` but relocate cleanly (e.g. a collapsible "Insights"
area or a tab) — don't scatter them.

**Finalize UX:** button "Lưu vào thư viện CV" → "Đang phân tích CV…" (the analysis step) → success
"Đã lưu • Sẵn sàng ứng tuyển" + pill flip (from the lifecycle work). Quota-full → existing modal.

**i18n:** vi/en for all new copy; ALSO map the backend `cv_empty` / `cv_quota_reached` reason codes
to localized frontend copy (fix the "Vietnamese message on /en" issue) instead of echoing
`ApiError.message`.

## Design bar

v9 Monochrome (`docs/DESIGN.md` §1.1.2) for the app chrome/inspector; the CV DOCUMENT stays
colorful per theme. Modern, tinh gọn, real recruitment-editor feel. Deliberate hover/active/
selected/disabled/loading/focus states. Responsive 375/768/1024/1440, light+dark. Reference:
Canva Resume / Zety / Novoresume editors (structured, not free-canvas).

## Out of scope (later)

- Full free-canvas (arbitrary x/y placement) — rejected for a CV product (ATS/matching/PDF).
- Drag-drop reordering upgrade (optional; up/down + outline already work).
- Real AI enrichment (embeddings/competencies) behind the finalize seam.

## Tests / verification

- Backend: elementStyles validation (good/bad), typed-link persistence, finalize analysis produces
  a stored matching payload + stays idempotent/quota-gated/non-empty; existing suite green.
- Frontend: typecheck/lint/build/vitest/i18n-parity green.
- Browser (I do this): tabbed inspector, AI chat request→diff→accept/reject→version, contextual
  toolbar changes font/size/color/align and persists, add a LinkedIn/GitHub link with icon,
  version restore, finalize analysis + pill flip, responsive.
